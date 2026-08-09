# r10b 片K · 构建、打包、安装器与端到端测试 —— 底稿

> 层:**L2**(读接口面,不读实现体;接口面不抽样)。
> 片内 **149 文件 / 22,551 行**,全部在 `/home/user/hermes-agent/` 下。
> 溯源约定:凡对代码的断言,锚点写成 `路径:行号 @ 863e313`,**单独成行、置于块前**。
> 基线自检:`git -C /home/user/hermes-agent status --porcelain` 为空,`HEAD = 863e313…`。

---

## 0. 本片范围与逐文件点名(判据 1)

本片是 hermes-agent 的**出厂线**:把源码变成用户能双击的东西,再证明那个东西能开机。
它由**三个互不相同的程序**加一层配置构成——

| 块 | 文件数 | 是什么 |
|---|---|---|
| A. Tauri + Rust 引导安装器 `apps/bootstrap-installer/` | 35 | 一个**独立的 Rust GUI 程序**(`Hermes-Setup.exe`),把 `scripts/install.ps1` / `install.sh` 从网上取下来并分阶段驱动;同一个二进制带 `--update` 时变成更新器 |
| B. Electron 桌面的构建/打包脚本 `apps/desktop/scripts/` | 74 | electron-builder 钩子链 + 原生依赖暂存 + 签名/公证 + 一整套 CDP 诊断与 perf 基准 |
| C. Playwright 端到端 `apps/desktop/e2e/` | 25 | 真 Electron + 真 `hermes serve` + **假模型**的黑盒测试,含一个可编脚本的 OpenAI 兼容 mock 服务器 |
| D. `apps/desktop/` 根下构建配置与自绘地图 | 15 | vite / vitest / playwright / 三份 tsconfig / package.json(51 条 npm script + 整个 electron-builder 配置)/ AGENTS.md / DESIGN.md / README.md |

合计 35 + 74 + 25 + 15 = **149**。

### 0.A `apps/bootstrap-installer/`(35)

**Rust 侧(src-tauri,13 文件 / 4,585 行)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/bootstrap-installer/src-tauri/Cargo.toml` | crate 清单:`[[bin]] name = "Hermes-Setup"` 决定磁盘上的文件名;release profile 用 `panic="abort"` + LTO 压到 5–10 MB |
| `apps/bootstrap-installer/src-tauri/build.rs` | 构建脚本:把 install 脚本的 **commit / branch pin** 用 `cargo:rustc-env=BUILD_PIN_*` 编进二进制;默认只 pin 分支(跟 HEAD 走),commit pin 靠 `HERMES_BUILD_PIN_COMMIT` 显式开启 |
| `apps/bootstrap-installer/src-tauri/src/main.rs` | 19 行进程入口;唯一实质内容是 `windows_subsystem = "windows"` 属性(必须挂在 bin crate 上,挂 lib 上曾留下一个游离的 cmd 窗口) |
| `apps/bootstrap-installer/src-tauri/src/lib.rs` | Tauri `run()`:解析 `--update` / `--reinstall` / `--repair`,装 4 个插件,注册 **9 个命令**,macOS 上有一条「已装则直接开 App 不显示安装器」的快速路径 |
| `apps/bootstrap-installer/src-tauri/src/bootstrap.rs` | 安装编排:取 manifest → 逐 stage 调 install 脚本 → 发事件 → 写 `.hermes-bootstrap-complete` 标记(临时文件 + rename 原子发布)→ 把自己拷进 HERMES_HOME |
| `apps/bootstrap-installer/src-tauri/src/install_script.rs` | 解析并**下载** install 脚本:dev 检出 → (未实现的)内置 → GitHub raw;commit pin 视为不可变可永久缓存,分支 pin 每次刷新、失败才回落陈旧缓存;`.ps1` 落盘时补 UTF-8 BOM |
| `apps/bootstrap-installer/src-tauri/src/powershell.rs` | 子进程驱动层:Windows 走 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`,Unix 走 `bash`;逐字节读行 + CP1252 回落解码;从 stdout **末尾**倒着找 JSON 结果帧 |
| `apps/bootstrap-installer/src-tauri/src/update.rs` | 更新编排(1,641 行,本片最长):等旧桌面释放文件锁 → `hermes update` → `hermes desktop --build-only` → macOS 上 ditto 换 `.app` → 重启桌面;含跨进程更新锁 `UpdateMarkerGuard` |
| `apps/bootstrap-installer/src-tauri/src/paths.rs` | HERMES_HOME 解析(必须与 Python / install.sh / Electron 三方一致)、日志初始化、把安装器自拷到 `HERMES_HOME/hermes-setup.exe`、3 个诊断命令 |
| `apps/bootstrap-installer/src-tauri/src/events.rs` | Rust→React 的事件类型定义:单通道 `"bootstrap"`,5 个 `type` 变体 |
| `apps/bootstrap-installer/src-tauri/tauri.conf.json` | 窗口(880×620,**初始 `visible:false`**)、CSP、bundle targets、Windows WebView2 引导方式 |
| `apps/bootstrap-installer/src-tauri/capabilities/default.json` | Tauri v2 权限声明面:9 条 permission,只对 `main` 窗口生效 |
| `apps/bootstrap-installer/src-tauri/hermes-setup.manifest` | Windows 应用清单:`asInvoker`(关掉 UAC 安装器探测启发式)、PerMonitorV2 DPI、UTF-8 活动代码页、common-controls v6 |

**前端侧(src + 配置,22 文件)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/bootstrap-installer/package.json` | 12 条 npm script;依赖 `@tauri-apps/api` + 4 个 Tauri 插件的 JS 绑定 |
| `apps/bootstrap-installer/vite.config.ts` | 端口 5175(避开 web 5173 / desktop 5174),`clearScreen:false`,不监视 `src-tauri/**` |
| `apps/bootstrap-installer/tsconfig.json` | 严格模式 + `noUnusedLocals/Parameters`,引用 tsconfig.node.json |
| `apps/bootstrap-installer/tsconfig.node.json` | 只覆盖 `vite.config.ts` 的 composite 子工程 |
| `apps/bootstrap-installer/eslint.config.mjs` | 5 行,原样转发仓库根 `eslint.config.shared.mjs` |
| `apps/bootstrap-installer/index.html` | 12 行 Vite 入口,`#root` + `/src/main.tsx` |
| `apps/bootstrap-installer/.gitignore` | 忽略 `src-tauri/target/`、**`src-tauri/Cargo.lock`**、dist、日志等(Cargo.lock 见 §6 ■-1) |
| `apps/bootstrap-installer/src/main.tsx` | React 挂载 + `watchTheme()` |
| `apps/bootstrap-installer/src/app.tsx` | 4 屏 shell,路由就是一个 `$route` atom,没有 react-router |
| `apps/bootstrap-installer/src/store.ts` | **前端唯一的 Tauri 接缝**:6 个 action(invoke)+ 1 个事件监听器 + 一套 dev-only 假引导 |
| `apps/bootstrap-installer/src/theme.ts` | 跟随 OS 外观:先用 media query 抢第一帧,再用 Tauri 窗口主题(WebView2/WebKitGTK 的 `prefers-color-scheme` 不可靠)接管 |
| `apps/bootstrap-installer/src/styles.css` | 整份转发 `apps/desktop/src/styles.css`,只补 Nous 暗色种子值 |
| `apps/bootstrap-installer/src/vite-env.d.ts` | 1 行 `/// <reference types="vite/client" />` |
| `apps/bootstrap-installer/src/lib/utils.ts` | `cn()` = clsx + tailwind-merge |
| `apps/bootstrap-installer/src/routes/welcome.tsx` | 欢迎屏:HERMES AGENT 字标 + `[ INSTALL ]` 按钮 |
| `apps/bootstrap-installer/src/routes/progress.tsx` | 进度屏:阶段列表 + 进度条 + 可展开的实时日志栏 + Cancel |
| `apps/bootstrap-installer/src/routes/success.tsx` | 成功屏:`[ LAUNCH ]`,并把 launch 失败**显式渲染出来**(旧版吞掉 rejection,按钮看着像坏了) |
| `apps/bootstrap-installer/src/routes/failure.tsx` | 失败屏:错误文案 + Retry(按 mode 分安装/更新)+ Open logs |
| `apps/bootstrap-installer/src/components/button.tsx` | 从桌面 `ui/button.tsx` **逐字复制**的 shadcn Button(不用 DS Button,因其硬编码金棕品牌色) |
| `apps/bootstrap-installer/src/components/hackery-button.tsx` | `[ LABEL ]` 括号式 CTA,取自桌面 onboarding overlay |
| `apps/bootstrap-installer/src/components/loader.tsx` | 桌面 559 行多曲线 Loader 中**只搬一条曲线**(fourier-flow)的独立实现 |
| `apps/bootstrap-installer/src/components/brand-mark.tsx` | 白底 tile + `nous-girl.jpg` 品牌标 |

### 0.B `apps/desktop/scripts/`(74)

分组核对:打包主链 11 + 签名/公证/身份 3 + 打包验证与开发启动 5 + perf 框架 23 +
脚本自测 4 + 诊断/探针/开发工具 28 = **74**。

**打包主链(11)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/scripts/utils.mjs` | 7 行:`isMain(import.meta.url)`,让脚本既能被 import 又能当 CLI |
| `apps/desktop/scripts/assert-root-install.mjs` | 11 行守卫:仓库根没装 `vite` 就报「先 `cd <root> && npm ci`」 |
| `apps/desktop/scripts/write-build-stamp.mjs` | 生成 `build/install-stamp.json`(schemaVersion/commit/branch/builtAt/dirty/source),来源优先级 CI env → 本地 git → 全零 fallback |
| `apps/desktop/scripts/bundle-electron-main.mjs` | esbuild 把 `electron/main.ts`→`dist/electron-main.mjs`(ESM)、`preload.ts`→`dist/electron-preload.js`(CJS);非 `--dev` 时 define 死 `HERMES_DESKTOP_IS_PACKAGED=true` |
| `apps/desktop/scripts/stage-native-deps.mjs` | 把 node-pty 的原生产物暂存进 `dist/node_modules/node-pty`,按魔数校验每个 `.node` 的目标平台,fail-closed |
| `apps/desktop/scripts/assert-dist-built.mjs` | `postbuild` 守卫:dist/index.html 存在且非空、dist/assets 里有 `.js`,否则拒绝进入打包 |
| `apps/desktop/scripts/patch-electron-builder-mac-binary.mjs` | `prebuilder` 钩子:**就地字符串替换 `node_modules/app-builder-lib/.../electronMac.js`**,补一条 Electron 主二进制丢失时的回填 |
| `apps/desktop/scripts/run-electron-builder.mjs` | 运行时解析本地 electron dist 并作为 `-c.electronDist=` 传给 electron-builder(躲开它自己重解包坏 Electron.app 的 bug) |
| `apps/desktop/scripts/before-build.mjs` | electron-builder `beforeBuild` 钩子,`return false` = 跳过 node_modules 收集 |
| `apps/desktop/scripts/before-pack.mjs` | `beforePack` 钩子:清理/备份上一次 unpacked 目录(Windows 保留 `.bak` 供回滚),并**按目标 arch 重新暂存 node-pty** |
| `apps/desktop/scripts/after-pack.mjs` | `afterPack` 钩子:Windows 上调 rcedit 打图标与身份 |

**签名 / 公证 / 身份(3)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/scripts/notarize.mjs` | `afterSign` 钩子:macOS 上 ditto 打 zip → `xcrun notarytool submit --wait` → `stapler staple`;凭据缺失时**静默跳过** |
| `apps/desktop/scripts/notarize-artifact.mjs` | 同样的公证逻辑,但作为**独立 CLI** 对任意产物(dmg/zip)执行;凭据缺失时**报错退出**,且刻意不把参数写进错误消息(防凭据进 CI 日志) |
| `apps/desktop/scripts/set-exe-identity.mjs` | 直接调 rcedit 改 Hermes.exe 的 PE 资源(图标 + ProductName/CompanyName…);存在的原因是 `signAndEditExecutable:false` 把 electron-builder 自己的 rcedit 一起关掉了 |

**打包验证 / 开发启动(5)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/scripts/test-desktop.mjs` | 6 种模式(existing/fresh/dmg/nsis/all/help)的手动验收器:打包 → `validateBundle()` 断言瘦安装器形态 → 启动(fresh 模式建沙箱并剥光凭据类环境变量) |
| `apps/desktop/scripts/dev-mock.mjs` | 用 e2e 的 mock 服务器 + 隔离 config 启动桌面,无需真 API key |
| `apps/desktop/scripts/dev-no-hmr.mjs` | 关掉 HMR 起 vite,绕开 Vite 8 + plugin-react 6 的 Fast Refresh preamble 注入缺陷 |
| `apps/desktop/scripts/rebuild-native.mjs` | `@electron/rebuild` 单独重编 node-pty(**不被任何 npm script 引用**,见 §6 ■-8) |
| `apps/desktop/scripts/gen-share-codes.ts` | 一次性生成器:假 star-map 图 → 真 share code(跑真编码器保证可 round-trip),输出 `share-codes.txt` |

**perf 基准框架(23)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/scripts/perf/README.md` | perf 框架自绘地图:快速上手、dev/prod 差异、隔离理由、场景表、如何加场景 |
| `apps/desktop/scripts/perf/run.mjs` | 入口:解析参数 → 选场景 → 可选 `--spawn` 隔离实例 / `--cpuprofile` → 与 baseline 对比并作为回归闸门 |
| `apps/desktop/scripts/perf/serve.mjs` | 只起一个隔离实例并停在那儿,供反复 attach |
| `apps/desktop/scripts/perf/baseline.json` | 提交进仓库的基准值,含 6 个场景条目 + `_meta`(平台/node/更新时间) |
| `apps/desktop/scripts/perf/lib/cdp.mjs` | 唯一的 CDP 客户端 + target 发现 + 打字模拟 + CPU profile 包装 + DOM 选择器常量 |
| `apps/desktop/scripts/perf/lib/stats.mjs` | 百分位、中位数、帧直方图、CPU profile self-time 排名 |
| `apps/desktop/scripts/perf/lib/baseline.mjs` | 载入/对比/更新 baseline 与容差闸门 |
| `apps/desktop/scripts/perf/lib/launch.mjs` | attach 到既有实例,或起一个自带 user-data-dir + HERMES_HOME + 调试端口的隔离实例;还负责 `--prod` 渲染器构建与 cold-start 采样 |
| `apps/desktop/scripts/perf/scenarios/index.mjs` | 场景注册表:14 个场景,`CI_SCENARIOS` = tier 为 `ci` 的那些 |
| `apps/desktop/scripts/perf/scenarios/stream.mjs` | tier `ci`:流式输出的 longtask / 帧 p95p99 / mutation 节奏 |
| `apps/desktop/scripts/perf/scenarios/stream-history.mjs` | tier **`manual`**:带历史的流式(README 场景表未列) |
| `apps/desktop/scripts/perf/scenarios/keystroke.mjs` | tier `ci`:输入框击键→上屏延迟 |
| `apps/desktop/scripts/perf/scenarios/transcript.mjs` | tier `ci`:大 transcript 挂载与绘制成本 |
| `apps/desktop/scripts/perf/scenarios/multitab.mjs` | tier **`ci`**:多 tab 同时流(README 场景表未列,但在默认套件和 baseline 里) |
| `apps/desktop/scripts/perf/scenarios/render-churn.mjs` | tier `ci`:逐组件渲染归因 + store 抖动 |
| `apps/desktop/scripts/perf/scenarios/idle-cost.mjs` | tier `report`:忙而静默的 tile 的空转 commit 率 |
| `apps/desktop/scripts/perf/scenarios/right-pane.mjs` | tier `report`:文件树 + 常驻 xterm 在拖拽下的表现 |
| `apps/desktop/scripts/perf/scenarios/cold-start.mjs` | tier `cold`:启动→CDP→首帧 |
| `apps/desktop/scripts/perf/scenarios/first-token.mjs` | tier `backend`:回车→首 token 上屏(TTFT) |
| `apps/desktop/scripts/perf/scenarios/submit.mjs` | tier `backend`:回车→清空→用户消息上屏 + 滚动跳变 |
| `apps/desktop/scripts/perf/scenarios/session-load.mjs` | tier `backend`:首帧后 transcript 还会移动多远 |
| `apps/desktop/scripts/perf/scenarios/session-switch.mjs` | tier `backend`:路由→首帧→稳定 |
| `apps/desktop/scripts/perf/scenarios/profile-switch.mjs` | tier `backend`:侧栏 profile 切换 |

**诊断 / 探针 / 开发工具(28 = 16 个 `diag-*` + 4 个 `probe-*` + 1 个 `profile-*` +
1 篇调查日志 + eval/reload/reload-renderer/click-session/live-drive 5 个 + 1 个 `.gitignore`)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/scripts/diag-code-live.mjs` | 查运行中渲染器**实际服务的源码**里 tree-split 预览路径是否生效 |
| `apps/desktop/scripts/diag-drag-churn.mjs` | 拖 sash 时是谁在重渲染 transcript:渲染归因 + 每个通知的 nanostores atom |
| `apps/desktop/scripts/diag-drag-trace.mjs` | 一次拖拽的真 CDP trace,按 Style/Layout/Paint/Script 拆时间 |
| `apps/desktop/scripts/diag-jump.mjs` | 包装 thread scroller 的属性,记录 submit 期间的 pin/scroll/RO 事件时间线 |
| `apps/desktop/scripts/diag-key-latency.mjs` | 有流 / 无流两种情况下的击键→下一帧延迟 |
| `apps/desktop/scripts/diag-live-state.mjs` | 通过 CDP 快速探活跑着的 hgui 状态 |
| `apps/desktop/scripts/diag-overlay-ab.mjs` | 对每个 overlay 面测 N 次取中位数的 A/B 浪费渲染量 |
| `apps/desktop/scripts/diag-overlay-churn.mjs` | 只读地量 cmdk/settings/command-center/skills 的渲染抖动 |
| `apps/desktop/scripts/diag-overlay-full.mjs` | 全 overlay 综合测量(**硬编码了作者机器的 devtools page id**,见 §6 ■-6) |
| `apps/desktop/scripts/diag-overlay-sweep.mjs` | 全面扫每个 overlay / settings 子页 / 系统 overlay(同样硬编码 id,但可用 `CDP_WS` 覆盖) |
| `apps/desktop/scripts/diag-real-loop.mjs` | 拿真实例跑「切会话 / 拖侧栏 / 打字」三件事,给单一时钟的诚实数字 |
| `apps/desktop/scripts/diag-ro-storm.mjs` | 一次拖拽触发多少 ResizeObserver 回调、覆盖多少不同元素 |
| `apps/desktop/scripts/diag-scroll-reset.mjs` | 复现并诊断「向上滚动看旧内容时视图被拽走」(`overflow-anchor` 假说) |
| `apps/desktop/scripts/diag-sidebar-dom.mjs` | dump 侧栏真实 DOM 结构,让选择器不再靠猜 |
| `apps/desktop/scripts/diag-switch-autopsy.mjs` | 在两个最重的会话行之间反复切,逐次记录 settled ms / React commit / top 组件 |
| `apps/desktop/scripts/diag-switch-trace.mjs` | 一次慢切换的 trace + 顶层调用点 |
| `apps/desktop/scripts/probe-command-palette.mjs` | ⌘K 打开延迟,在页内计时(不含 CDP 往返) |
| `apps/desktop/scripts/probe-model-picker.mjs` | 模型选择器打开延迟 |
| `apps/desktop/scripts/probe-renderer.mjs` | 最小探针:读渲染器状态 |
| `apps/desktop/scripts/probe-thread.mjs` | 探 thread 状态:消息数、turn 对数、高度、composer 状态 |
| `apps/desktop/scripts/profile-model-picker.mjs` | 对一次模型选择器打开做 CPU profile |
| `apps/desktop/scripts/profile-typing-lag.md` | 388 行调查日志:如何经验性测量并修输入延迟(开头已注明工具已被 `scripts/perf/` 取代) |
| `apps/desktop/scripts/eval.mjs` | `node scripts/eval.mjs "<expr>"` 在渲染器里求值 |
| `apps/desktop/scripts/reload.mjs` | CDP 硬刷新渲染器(no-HMR 模式下改完代码用) |
| `apps/desktop/scripts/reload-renderer.mjs` | 同上的另一个变体(按 target 类型找页面) |
| `apps/desktop/scripts/click-session.mjs` | 按标题模糊匹配点一个会话 |
| `apps/desktop/scripts/live-drive.mjs` | 对真实例的驱动台:`status` / `fps [秒]` / `drag` / `type` / `switch` / `send "msg"` 六个子命令,报 fps 与 LoAF |
| `apps/desktop/scripts/.gitignore` | 1 行:忽略 `share-codes.txt`(gen-share-codes.ts 的产物) |

**脚本自测(4,本片唯一能在本容器跑的测试)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/scripts/assert-dist-built.test.mjs` | 钉住 `checkDistBuilt` 的四种失败与一种通过 |
| `apps/desktop/scripts/before-pack.test.mjs` | 钉住 `cleanStaleAppOutDir` / `preserveRollbackBackup` 的判定与回滚保留条件 |
| `apps/desktop/scripts/stage-native-deps.test.mjs` | 钉住魔数分类 `classifyNativeBinary` 与 `stageNodePtyInto` 的 fail-closed 行为 |
| `apps/desktop/scripts/write-build-stamp.test.mjs` | 钉住 stamp 三档来源优先级与全零 fallback 判定 |

### 0.C `apps/desktop/e2e/`(25)

**基础设施(6)**

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/e2e/test.ts` | 扩展的 Playwright fixture:任何 `[role="alert"]` 错误横幅出现就让用例失败;`allowErrorBanners()` 供故意触发错误的用例退出该守卫 |
| `apps/desktop/e2e/fixtures.ts` | 四种夹具(mockBackend / noProvider / deadBackend / packagedApp)+ 沙箱创建 + 凭据剥离 + `waitForAppReady` 等待条件 |
| `apps/desktop/e2e/mock-server.ts` | 可编脚本的 OpenAI 兼容 mock:`GET /v1/models` + `POST /v1/chat/completions`,按用户消息里的触发词切换 6 套脚本剧本 |
| `apps/desktop/e2e/real-session-builder.ts` | 用**真 stdio JSON-RPC TUI 网关**造持久会话历史(不 import SessionDB、不起 Electron) |
| `apps/desktop/e2e/visual-snapshot.ts` | 视觉快照包装:强制窗口尺寸 1220×800,自己用 Electron `nativeImage` 逐像素比对,**差异只报告不失败** |
| `apps/desktop/e2e/fix-electron-tracing.ts` | monkey-patch Playwright 私有符号(`_allContexts` / `_context`),让 Electron context 的 trace 能被录到并合并 |

**19 个 spec**

| 全路径 | 一句话角色 | 用例数 |
|---|---|---|
| `apps/desktop/e2e/boot.spec.ts` | dev 模式 + mock 后端的开机冒烟:标题、DOM 挂载、就绪、截图 | 4 |
| `apps/desktop/e2e/boot-failure.spec.ts` | 注入假 boot 错误,断言错误态 overlay | 2 |
| `apps/desktop/e2e/launch-packaged-app.spec.ts` | 启动**打包后**的二进制(`npm run pack` 产物),没产物就整文件 skip | 4 |
| `apps/desktop/e2e/mock-backend-setup.spec.ts` | mock 后端能越过 onboarding:无 overlay、composer 可见可输入、截图 | 4 |
| `apps/desktop/e2e/onboarding.spec.ts` | 空 config 时出 provider 选择器 | 3 |
| `apps/desktop/e2e/chat.spec.ts` | 发一条消息收到回复;忙时提供 stop/steer/queue | 3 |
| `apps/desktop/e2e/interim-messages.spec.ts` | #65919:中间态 assistant 消息在 flag ON/OFF 两种配置下的存留 | 2 |
| `apps/desktop/e2e/hidden-history-messages.spec.ts` | 压缩交接行与 verify-on-stop 续写不得出现在 transcript | 2 |
| `apps/desktop/e2e/queue-turn-boundary.spec.ts` | 排队的 prompt 必须等当前 turn 结束才提交;steer 必须插在被改向的回复之前 | 2 |
| `apps/desktop/e2e/session-compression-and-queue-stop.spec.ts` | 压缩会话后能在续体上接着发;压缩进行中回车应排队而非 steer | 2 |
| `apps/desktop/e2e/correction-session-switch.spec.ts` | 直播中发纠正 + 热切会话来回,纠正不得重复或错位 | 2 |
| `apps/desktop/e2e/large-session-resume.spec.ts` | 大会话冷/热恢复:一行用户消息、transcript 重绘有界(含 1 条 `test.fixme`) | 4 |
| `apps/desktop/e2e/warm-resume-jitter.spec.ts` | 热路径恢复不得重绘多于一次(含 1 条 `test.fixme`) | 2 |
| `apps/desktop/e2e/image-attachment-resume.spec.ts` | 附件图片在冷重载后仍渲染成缩略图 | 1 |
| `apps/desktop/e2e/sidebar-states.spec.ts` | 侧栏后台进程点 / 子代理 / 跨会话点状态迁移 | 3 |
| `apps/desktop/e2e/tile-unread-bug.spec.ts` | tab(隐藏)未读点正确 = 通过;split(可见)未读点 = **整块 `describe.skip`(已知红灯)** | 2 |
| `apps/desktop/e2e/submit-drift.spec.ts` | #69578:新建会话时的路由 token 抖动不得吞掉 prompt | 1 |
| `apps/desktop/e2e/right-pane.spec.ts` | 常驻终端 overlay 在拖分栏后仍跟随窗格 | 1 |
| `apps/desktop/e2e/worktree-branch-status.spec.ts` | worktree 对话框:分支选择器不被裁剪、列出分支、ctrl-shift-b 建分支后 composer git 状态更新、只开一个对话框 | 4 |
| | **合计** | **47** |

### 0.D `apps/desktop/` 根下(15)

| 全路径 | 一句话角色 |
|---|---|
| `apps/desktop/package.json` | 本片的中枢:**51 条 npm script** + 完整 electron-builder `build` 配置(targets / 4 个钩子 / entitlements / asarUnpack / nsis 选项) |
| `apps/desktop/vite.config.ts` | 渲染器构建:`fs.allow` 白名单(worktree symlink)、空 PostCSS 固化、emojibase 离线资产插件、`advancedChunks` 手工分包、dev-only 调试图的别名开关 |
| `apps/desktop/vitest.config.ts` | 两个 project:`ui`(jsdom,`src/**/*.test.{ts,tsx}`)与 `electron`(node,`electron/**/*.test.ts` + `scripts/**.test.{ts,mjs}`) |
| `apps/desktop/vitest.setup.ts` | jsdom 侧补 `localStorage`(Node 26 的同名 accessor 会遮蔽 jsdom 的)、开 act 环境、放宽 `asyncUtilTimeout` |
| `apps/desktop/playwright.config.ts` | e2e 配置:`testDir: './e2e'`、90s 超时、`fullyParallel:false`、trace/screenshot 全开、`reducedMotion:'reduce'`、截图 1% 容差 |
| `apps/desktop/tsconfig.json` | 渲染器工程,`exclude: ["e2e","electron","playwright.config.ts"]` |
| `apps/desktop/tsconfig.electron.json` | 主进程工程,**逐条关掉 strict 家族**,composite + declaration 输出到 `build/electron-types` |
| `apps/desktop/tsconfig.e2e.json` | 9 行,e2e 工程,types 加 `@playwright/test` |
| `apps/desktop/eslint.config.mjs` | 转发共享配置 + 补 browser globals + **插件围栏**(`src/plugins/**` 只准 import `@hermes/plugin-sdk`)+ 禁「用 useEffect 把 atom 镜像进 ref」的 AST 规则 |
| `apps/desktop/index.html` | 渲染器 HTML;内联脚本从 localStorage 预涂主题背景色,消掉新窗口白闪 |
| `apps/desktop/preview-demo.html` | 65 行独立静态页,给右侧预览窗格当演示素材 |
| `apps/desktop/components.json` | shadcn CLI 配置(style new-york,icon library tabler) |
| `apps/desktop/AGENTS.md` | 自绘地图:桌面工程判断准则(状态归属、身份、切换形态、可观测阶梯、性能、测试) |
| `apps/desktop/DESIGN.md` | 自绘地图:设计系统契约(token、Button 变体、层级、动效、i18n、检查清单) |
| `apps/desktop/README.md` | 自绘地图:安装、更新、开发、**构建安装器**、工作原理、验证命令、排障 |

---

## 1. 这一簇解决什么问题

一个 agent harness 要交付给不会用终端的人,得跨过四道坎,这一片正好一坎一块:

1. **怎么把一堆 TS/Rust/Python 变成一个可双击的东西** —— electron-builder 钩子链(§2.3)。
2. **怎么在用户机器上装出一个完整运行时**,而运行时本身是一份要 clone 的 Python 仓库 —— 引导安装器(§2.4)。它的取舍很特别:**安装器不带负载**,只带一个 pin,负载在安装时从 GitHub 现取(README 称之为 thin installer;`apps/desktop/scripts/test-desktop.mjs` 甚至有一条**反向断言**防止旧的 400 MB 胖负载偷偷回来,见 §5 ◎-1)。
3. **怎么在不花模型钱、不连真 provider 的前提下证明整条链是通的** —— e2e 的 mock provider(§2.6)。
4. **怎么让性能回归有一个能被 CI 挡住的数** —— perf 基准框架(§2.7)。

这一片最值得学的一条设计:**安装器与更新器是同一个二进制**(`--update` 切模式),因此
「安装」和「更新」共用同一套事件通道、同一个进度 UI —— 更新流程只是把真实 manifest 换成一份
**合成 manifest**(`apps/bootstrap-installer/src-tauri/src/update.rs` 的 `update_stages`),前端一行都不用改。

---

## 2. 接缝穷举(判据 2)

### 2.1 `apps/desktop` 的 51 条 npm script(全表,不抽样)

枚举命令与条数:

```verify
cd /home/user/hermes-agent && python3 -c \
  "import json;print(len(json.load(open('apps/desktop/package.json'))['scripts']))"
# => 51
```

`apps/desktop/package.json` 的 `scripts` 块共 51 条,按用途分组列全:

| # | script | 做什么 |
|---|---|---|
| 1 | `clean` | 串起下面三条 clean |
| 2 | `clean:e2e` | `tsc --build tsconfig.e2e.json --clean` |
| 3 | `clean:renderer` | `tsc --build tsconfig.json --clean` |
| 4 | `clean:electron` | `tsc --build tsconfig.electron.json --clean` |
| 5 | `dev` | concurrently 起 `dev:renderer` + `dev:electron` |
| 6 | `dev:fake-boot` | 带 `HERMES_DESKTOP_BOOT_FAKE=1` 的 dev,演示开机 overlay |
| 7 | `dev:mock` | `node scripts/dev-mock.mjs` |
| 8 | `dev:renderer` | 根安装守卫 → clean → `vite --host 127.0.0.1 --port 5174` |
| 9 | `dev:electron` | 编 electron 工程 → 等 5174 → bundle `--dev` → `electron .` |
| 10 | `profile:main` | 同 9,但 `electron --inspect=9229` |
| 11 | `profile:main:cpu` | 同 9,但 `NODE_OPTIONS=--cpu-prof` |
| 12 | `start` | `build` 后 `electron .` |
| 13 | `prebuild` | = `clean`(npm 生命周期自动挂在 `build` 前) |
| 14 | `build` | 根守卫 → 写 stamp → `vite build` → bundle 主进程 → 暂存 node-pty |
| 15 | `postbuild` | `assert-dist-built.mjs` |
| 16 | `prebuilder` | `patch-electron-builder-mac-binary.mjs` |
| 17 | `builder` | `NODE_OPTIONS=--max-old-space-size=16384 node scripts/run-electron-builder.mjs` |
| 18 | `pack` | `build && builder -- --dir`(只出 unpacked) |
| 19 | `dist` | `build && builder`(当前平台全默认 target) |
| 20 | `dist:mac` | `-- --mac` |
| 21 | `dist:mac:dmg` | `-- --mac dmg` |
| 22 | `dist:mac:zip` | `-- --mac zip` |
| 23 | `dist:win` | `-- --win` |
| 24 | `dist:win:msi` | `-- --win msi` |
| 25 | `dist:win:nsis` | `-- --win nsis` |
| 26 | `dist:linux` | `-- --linux AppImage deb rpm` |
| 27 | `perf` | `node scripts/perf/run.mjs` |
| 28 | `perf:serve` | `node scripts/perf/serve.mjs` |
| 29 | `test:desktop` | `node scripts/test-desktop.mjs`(无参数 = help) |
| 30 | `test:desktop:all` | 同上 `all` |
| 31 | `test:desktop:dmg` | 同上 `dmg` |
| 32 | `test:desktop:nsis` | 同上 `nsis` |
| 33 | `test:desktop:existing` | 同上 `existing` |
| 34 | `test:desktop:fresh` | 同上 `fresh` |
| 35 | `typecheck` | 三个 tsconfig 各跑一次 `--noEmit` |
| 36 | `lint` | `eslint src/ electron/` |
| 37 | `lint:fix` | 同上 `--fix` |
| 38 | `fmt` | prettier 写 `src/**`、`electron/**`、`vite.config.ts` |
| 39 | `fix` | `lint:fix && fmt` |
| 40 | `test:ui` | `vitest run --project ui` |
| 41 | `test:desktop:platforms` | `vitest run --project electron` |
| 42 | `test` | `vitest run`(两个 project) |
| 43 | `preview` | 根守卫 + `vite preview --port 4174` |
| 44 | `check:test:desktop:platforms` | → 41 |
| 45 | `check:test:ui` | → 40 |
| 46 | `check:test:desktop:all` | → 30 |
| 47 | `check:lint` | `typecheck && lint` |
| 48 | `check` | 47 → 45 → 41 → 30 |
| 49 | `test:e2e` | `build && playwright test e2e/` |
| 50 | `test:e2e:visual` | 同上,套 `cage`(headless wlroots)跑 |
| 51 | `test:e2e:update-snapshots` | 同上 + `--update-snapshots` |

**读这张表读出来的两件事**(都不写在任何文档里):

- 第 48 条 `check` 里含 `test:desktop:all`,而 `test:desktop:all` 在 Linux 上会调 `ensurePackagedApp()` → `npm run pack`。也就是说 **`npm run check` 会跑一次完整 electron-builder 打包**,不是一个纯静态检查。
- `build`(第 14 条)**不含任何 `tsc`**;渲染器类型检查只在 `typecheck`(第 35 条)里发生。`prebuild`→`clean` 里的 `tsc --build --clean` 只是删产物。

`apps/desktop/package.json:27 @ 863e313`

```
    "build": "node scripts/assert-root-install.mjs && node scripts/write-build-stamp.mjs && vite build && node scripts/bundle-electron-main.mjs && node scripts/stage-native-deps.mjs",
    "postbuild": "node scripts/assert-dist-built.mjs",
```

### 2.2 `apps/bootstrap-installer` 的 12 条 npm script(全表)

```verify
cd /home/user/hermes-agent && python3 -c \
  "import json;print(len(json.load(open('apps/bootstrap-installer/package.json'))['scripts']))"
# => 12
```

`dev`(vite 5175)、`build`(`tsc -b && vite build`)、`preview`、`tauri`、`tauri:dev`、
`tauri:build`、`tauri:build:debug`、`typecheck`、`check`、`lint`、`lint:fix`、`fix`。
注意这里的 `build` **含 `tsc -b`**,而桌面的 `build` 没有(§2.1)。

### 2.3 打包产物矩阵(electron-builder,全表)

枚举命令与结果:

```verify
cd /home/user/hermes-agent && python3 -c "
import json;b=json.load(open('apps/desktop/package.json'))['build']
print('artifactName', b['artifactName'])
for k in ('beforeBuild','beforePack','afterPack','afterSign'): print(k,'=',b.get(k))
for p in ('mac','win','linux'): print(p,'targets =',b[p]['target'])"
# artifactName Hermes-${version}-${os}-${arch}.${ext}
# beforeBuild = scripts/before-build.mjs
# beforePack  = scripts/before-pack.mjs
# afterPack   = scripts/after-pack.mjs
# afterSign   = scripts/notarize.mjs
# mac   targets = ['dmg', 'zip']
# win   targets = ['nsis', 'msi']
# linux targets = ['AppImage', 'deb', 'rpm']
```

| 平台 | 默认 target | 走哪条 npm script | 平台特有处理 |
|---|---|---|---|
| macOS | `dmg`, `zip` | `dist:mac` / `dist:mac:dmg` / `dist:mac:zip` | `hardenedRuntime:true` + 两份 entitlements;`extendInfo` 里三条隐私用途说明(音频/摄像头/麦克风);`gatekeeperAssess:false`;`afterSign` 公证;`prebuilder` 就地补丁 app-builder-lib |
| Windows | `nsis`, `msi` | `dist:win` / `dist:win:msi` / `dist:win:nsis` | `signAndEditExecutable:false`;`afterPack` 用 rcedit 补图标与身份;nsis 为 `oneClick:false` + `perMachine:false`(**用户级安装**) |
| Linux | `AppImage`, `deb`, `rpm` | `dist:linux`(**显式列出三种**) | 只有 category/maintainer/synopsis |
| 任意 | unpacked 目录 | `pack`(`--dir`) | e2e 的 `launch-packaged-app.spec.ts` 依赖这个产物 |

**全平台共用的钩子链**(4 个钩子在 electron-builder 生命周期里的顺序):

`beforeBuild`(返回 false,跳过依赖收集)→ `beforePack`(清/备份 unpacked + 按目标 arch 重暂存 node-pty)→ 打包 → `afterPack`(Windows rcedit)→ 签名 → `afterSign`(macOS 公证)。
外加两条由 npm 生命周期挂的:`prebuild`=clean、`postbuild`=assert-dist-built、`prebuilder`=打补丁。

打包内容面(同一份配置):`files` = `dist/**` `assets/**` `public/**` `package.json`;
`asar:true` 但 `asarUnpack` = `**/*.node`、`**/prebuilds/**`、`dist/**`;
`extraResources` = `build/install-stamp.json` → `install-stamp.json`、`assets/icon.ico` → `icon.ico`;
`protocols` 注册 `hermes://` scheme。

### 2.4 Tauri 命令面(9 条,全表)

`apps/bootstrap-installer/src-tauri/src/lib.rs:168 @ 863e313`

```
        .invoke_handler(tauri::generate_handler![
            // Mode (install vs update)
            get_mode,
            // Bootstrap lifecycle
            bootstrap::start_bootstrap,
            bootstrap::cancel_bootstrap,
            bootstrap::get_bootstrap_status,
            // Update lifecycle
            update::start_update,
            // Hand-off
            bootstrap::launch_hermes_desktop,
            // Diagnostics
            paths::get_log_path,
            paths::get_hermes_home,
            paths::open_log_dir,
        ])
```

机械核对「注册数 == `#[tauri::command]` 数」:

```verify
cd /home/user/hermes-agent/apps/bootstrap-installer/src-tauri && \
  grep -rc "#\[tauri::command\]" src/*.rs | grep -v ":0"
# src/bootstrap.rs:4  src/lib.rs:1  src/paths.rs:3  src/update.rs:1   => 9
```

| 命令 | 定义处 | 入参 | 出参 | 前端调用点 |
|---|---|---|---|---|
| `get_mode` | `apps/bootstrap-installer/src-tauri/src/lib.rs:90` 的 `fn get_mode` | — | `"install" \| "update"` | `apps/bootstrap-installer/src/store.ts:195`:`invoke<AppMode>('get_mode')` |
| `start_bootstrap` | `apps/bootstrap-installer/src-tauri/src/bootstrap.rs:73` 的 `pub async fn start_bootstrap` | `StartBootstrapArgs{commit,branch,include_desktop,hermes_home}` | `Result<(),String>` | `apps/bootstrap-installer/src/store.ts:315`:`await invoke('start_bootstrap', {` |
| `cancel_bootstrap` | `apps/bootstrap-installer/src-tauri/src/bootstrap.rs:130` 的 `pub async fn cancel_bootstrap` | — | `Result<(),String>` | `apps/bootstrap-installer/src/store.ts:347`:`await invoke('cancel_bootstrap')` |
| `get_bootstrap_status` | `apps/bootstrap-installer/src-tauri/src/bootstrap.rs:139` 的 `pub async fn get_bootstrap_status` | — | `BootstrapStatus{running,completed,install_root,last_error}` | **前端无调用点**(见 §6 ■-9) |
| `start_update` | `apps/bootstrap-installer/src-tauri/src/update.rs:61` 的 `pub async fn start_update` | — | `Result<(),String>` | `apps/bootstrap-installer/src/store.ts:337`:`await invoke('start_update')` |
| `launch_hermes_desktop` | `apps/bootstrap-installer/src-tauri/src/bootstrap.rs:166` 的 `pub async fn launch_hermes_desktop` | `installRoot: String` | `Result<(),String>` | `apps/bootstrap-installer/src/store.ts:355`:`await invoke('launch_hermes_desktop', { installRoot })` |
| `get_log_path` | `apps/bootstrap-installer/src-tauri/src/paths.rs:200` 的 `pub fn get_log_path` | — | `String` | `apps/bootstrap-installer/src/store.ts:193`:`invoke<string>('get_log_path'),` |
| `get_hermes_home` | `apps/bootstrap-installer/src-tauri/src/paths.rs:205` 的 `pub fn get_hermes_home` | — | `String` | `apps/bootstrap-installer/src/store.ts:194`:`invoke<string>('get_hermes_home'),` |
| `open_log_dir` | `apps/bootstrap-installer/src-tauri/src/paths.rs:210` 的 `pub fn open_log_dir` | — | `Result<(),String>` | `apps/bootstrap-installer/src/store.ts:360`:`await invoke('open_log_dir')` |

### 2.5 Rust→React 事件面(1 通道 / 5 变体,全表)

通道名只有一个,靠 payload 的 `type` 字段分流。

`apps/bootstrap-installer/src-tauri/src/events.rs:111 @ 863e313`

```
    pub const CHANNEL: &'static str = "bootstrap";
```

| `type` | Rust 变体字段 | 前端处理(`apps/bootstrap-installer/src/store.ts`) |
|---|---|---|
| `manifest` | `stages: Vec<StageInfo>`, `protocolVersion: Option<u32>` | 建 stage 表与顺序,`status='running'`,路由跳 `progress`(:210) |
| `stage` | `name`, `state`, `durationMs?`, `result?`, `error?` | 打 `startedAt` 时间戳、更新 `currentStage`(:235) |
| `log` | `stage?`, `line`, `stream` | 追加进日志环形缓冲,**上限 2000 行**(:249) |
| `complete` | `installRoot`, `marker` | `status='completed'`;install 模式跳 `success`,**update 模式留在 progress**(:259) |
| `failed` | `stage?`, `error` | `status='failed'`,跳 `failure`(:277) |

`StageState` 枚举同样是 4 值封闭集(serde 以小写序列化):

`apps/bootstrap-installer/src-tauri/src/events.rs:45 @ 863e313`

```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum StageState {
    Running,
    Succeeded,
    Skipped,
    Failed,
}
```

前端 action 面(store 导出的全部 6 个 async 动作,不抽样):
`initialize()`、`startInstall(opts?)`、`startUpdate()`、`cancelInstall()`、
`launchHermesDesktop()`、`openLogDir()`;外加 5 个 atom:
`$route` `$mode` `$bootstrap` `$logPath` `$hermesHome` 与 1 个 computed `$progress`。

### 2.6 Tauri 权限声明面(9 条,全表)

`apps/bootstrap-installer/src-tauri/capabilities/default.json:6 @ 863e313`

```
  "permissions": [
    "core:default",
    "core:window:allow-close",
    "core:window:allow-minimize",
    "core:window:allow-theme",
    "core:event:default",
    "opener:default",
    "dialog:default",
    "process:default",
    "shell:default"
  ]
```

作用域只有 `"windows": ["main"]`。配套的 CSP:

`apps/bootstrap-installer/src-tauri/tauri.conf.json:30 @ 863e313`

```
      "csp": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self' data:; connect-src 'self' ipc: http://ipc.localhost"
```

`script-src 'self'` 明确禁掉内联脚本,这正是 `apps/bootstrap-installer/src/theme.ts` 不能在
index.html 里预涂主题、只能在打包模块里做首帧的原因(该文件开头的注释把这条 CSP 列为原因之一)。
`withGlobalTauri: false`,即 webview 里没有 `window.__TAURI__` 全局。

### 2.7 e2e 场景清单(19 spec / 47 用例,逐项已在 §0.C 列全)

枚举命令与条数:

```verify
cd /home/user/hermes-agent/apps/desktop && ls e2e/*.spec.ts | wc -l && \
  grep -hcE "^\s*test\(" e2e/*.spec.ts | paste -sd+ | bc
# 19
# 47
```

静态失效的用例(**必须点名,否则汇总里和「通过」长得一样**):

| 位置 | 形态 | 掩盖了几个用例 |
|---|---|---|
| `apps/desktop/e2e/tile-unread-bug.spec.ts:166`:`test.describe.skip('sidebar states — split (visible) unread bug (RED)', () => {` | 整个 describe 跳过 | 1 |
| `apps/desktop/e2e/large-session-resume.spec.ts:202`:`test.fixme(true, 'Fast warm resume has an unresolved third transcript rebuild')` | 单用例 fixme | 1 |
| `apps/desktop/e2e/warm-resume-jitter.spec.ts:397` 的 `test.fixme` | 单用例 fixme | 1 |
| `apps/desktop/e2e/launch-packaged-app.spec.ts:24` 的 `test.skip` | 运行期条件跳过(无打包产物时整文件跳) | 4 |

mock 服务器的**剧本触发词全表**(这是 e2e 的隐藏接口面,决定 mock 走哪条脚本):

| 触发词 / 条件 | 剧本常量 | 轮数 | 干什么 |
|---|---|---|---|
| 任意消息里含 `E2E_BLOCKING_CLARIFY_TRIGGER` | `BLOCKING_CLARIFY_TURN` | 1(可重复) | 发一个真的阻塞式 `clarify` 工具调用,把 turn 卡住 |
| `E2E_QUEUE_STOP_TRIGGER` | `QUEUE_STOP_SCRIPT` | 2 | clarify 卡住 → 完成 |
| `E2E_VERIFY_ON_STOP_TRIGGER` | `verificationStopScript(writePath)` | 3 | 真写文件 → 两次收尾尝试 |
| `E2E_CORRECTION_SWITCH_TRIGGER` | `CORRECTION_SWITCH_SCRIPT` | 2 | `terminal sleep 5` 卡住 → 完成 |
| `E2E_SIDEBAR_CROSS` | `sidebarCrossScript(releasePath)` | 2 | 长后台进程(可用哨兵文件控制寿命)+ 子代理 |
| `E2E_SIDEBAR_TRIGGER` | `SIDEBAR_SCRIPT` | 2 | 短后台进程 + 子代理 → 完成 |
| `E2E_INTERIM_TRIGGER` | `INTERIM_SCRIPT` | 5 | 文本+工具 ×2 → 纯工具无文本 → 文本+工具 → 终答 |
| 以上都不中 | `MOCK_REPLY` 定值 | — | 逐词 SSE 回一句罐头话 |

服务器只实现两个路由:`GET /v1/models`、`POST /v1/chat/completions`,其余一律 404。

`apps/desktop/e2e/mock-server.ts:533 @ 863e313`

```
      // Fallback — 404 for anything else
      res.writeHead(404, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'Not found' }))
```

### 2.8 perf 场景注册表(14 个,全表)

```verify
# 从任意 hermes-agent 检出的根目录执行(纯 import,不写任何文件):
cd apps/desktop/scripts/perf && node -e "
import('./scenarios/index.mjs').then(m => {
  console.log('SCENARIOS =', Object.keys(m.SCENARIOS).length, Object.keys(m.SCENARIOS).join(','));
  console.log('CI_SCENARIOS =', m.CI_SCENARIOS.length, m.CI_SCENARIOS.join(','));})"
# SCENARIOS = 14 stream,stream-history,keystroke,transcript,multitab,render-churn,
#             right-pane,idle-cost,cold-start,first-token,submit,session-load,
#             session-switch,profile-switch
# CI_SCENARIOS = 5 stream,keystroke,transcript,multitab,render-churn
```

(本轮实测跑在主线备好的**基线之外**副本上,以免在只读基线里留下任何痕迹;
这些场景模块无外部依赖,内容与基线逐字一致。)

tier 分布:`ci` ×5、`backend` ×5、`report` ×2、`cold` ×1、`manual` ×1。
baseline.json 里有条目的是 6 个:`stream / keystroke / transcript / cold-start / multitab / render-churn`
—— 即 5 个 ci + 1 个 cold,与 README「`ci` + `cold` 场景被 baseline 闸住」一致。

### 2.9 构建脚本的**导出面**(供 import 而非 CLI 的那些)

| 模块 | 导出 | 被谁 import |
|---|---|---|
| `apps/desktop/scripts/utils.mjs` | `isMain` | assert-dist-built / rebuild-native / set-exe-identity / stage-native-deps / write-build-stamp |
| `apps/desktop/scripts/assert-dist-built.mjs` | `checkDistBuilt`,default `{checkDistBuilt}` | 自测 |
| `apps/desktop/scripts/before-pack.mjs` | `cleanStaleAppOutDir`、`preserveRollbackBackup`、default `beforePack` | electron-builder + 自测 |
| `apps/desktop/scripts/stage-native-deps.mjs` | `classifyNativeBinary`、`stageNodePtyInto`、`stageNodePty` | before-pack.mjs + 自测 |
| `apps/desktop/scripts/write-build-stamp.mjs` | `FALLBACK_COMMIT`、`FALLBACK_BRANCH`、`fromCI`、`fromLocalGit`、`fromFallback`、`resolveStamp`、`isFallbackCommit` | 自测 |
| `apps/desktop/scripts/set-exe-identity.mjs` | `stampExeIdentity` | after-pack.mjs |
| `apps/desktop/scripts/rebuild-native.mjs` | `rebuildNodePty` | **无人** |
| `apps/desktop/scripts/notarize.mjs` | default `notarize` | electron-builder `afterSign` |
| `apps/desktop/scripts/before-build.mjs` | default `beforeBuild` | electron-builder `beforeBuild` |
| `apps/desktop/scripts/after-pack.mjs` | default `afterPack` | electron-builder `afterPack` |

---

## 3. 端到端链(判据 3):用户点 `[ INSTALL ]` 到第一个 stage 跑起来

逐跳带锚点,全部落在本片内。

**跳 1 · 用户动作 → 组件。** 欢迎屏上唯一的按钮。

`apps/bootstrap-installer/src/routes/welcome.tsx:45 @ 863e313`

```
      <HackeryButton label="Install" onClick={() => void startInstall()} />
```

**跳 2 · 组件 → 状态 + IPC。** store 先把状态清干净、路由推到 progress,再 invoke。
注意 `commit: null`:前端不传 pin,让 Rust 用编进二进制的 `BUILD_PIN_*`。

`apps/bootstrap-installer/src/store.ts:313 @ 863e313`

```
  $bootstrap.set(INITIAL)
  $route.set('progress')
  await invoke('start_bootstrap', {
    args: {
      commit: null,
      branch: opts?.branch ?? null,
      include_desktop: true,
      hermes_home: null
    }
  })
```

**跳 3 · IPC → Rust 命令。** 命令本身是 fire-and-forget:占住状态锁、建取消通道、
spawn 一个 tokio 任务就返回,进度全部走事件通道。

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:104 @ 863e313`

```
    tokio::spawn(async move {
        let result = run_bootstrap(app_for_task.clone(), args_for_task, cancel_rx).await;
```

**跳 4 · 决定 pin。** 前端给的是 `None`,于是回落到编译期常量。

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:451 @ 863e313`

```
    let pin = Pin {
        commit: args.commit.or_else(|| option_env_string("BUILD_PIN_COMMIT")),
        branch: args.branch.or_else(|| option_env_string("BUILD_PIN_BRANCH")),
    };
```

这两个常量由构建脚本注入;**默认只注入分支**,commit pin 要显式开:

`apps/bootstrap-installer/src-tauri/build.rs:107 @ 863e313`

```
    let requested = std::env::var("HERMES_BUILD_PIN_COMMIT").ok()?;
```

**跳 5 · 取脚本。** commit pin 不可变可永久复用缓存,分支 pin 每次都重下:

`apps/bootstrap-installer/src-tauri/src/install_script.rs:86 @ 863e313`

```
pub(crate) fn cache_plan(immutable: bool, cached_exists: bool) -> CachePlan {
    if immutable && cached_exists {
        CachePlan::Reuse
    } else {
        CachePlan::Fetch {
            stale_ok: !immutable && cached_exists,
        }
    }
}
```

需要下载时,URL 是写死的 GitHub raw:

`apps/bootstrap-installer/src-tauri/src/install_script.rs:325 @ 863e313`

```
async fn download(kind: ScriptKind, commit_or_ref: &str, dest_path: &Path) -> Result<()> {
    let url = format!(
        "https://raw.githubusercontent.com/NousResearch/hermes-agent/{}/scripts/{}",
        commit_or_ref,
        kind.filename()
    );
```

**跳 6 · 问 manifest。** 先用 `-Manifest` 拿阶段清单;`-IncludeDesktop` 必须在这一步也传,
否则回来的 manifest 里根本没有 desktop 阶段:

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:514 @ 863e313`

```
    let manifest_args = build_pin_args(&script);
    let mut manifest_args_full = vec!["-Manifest".to_string()];
    manifest_args_full.extend(manifest_args.clone());
    if args.include_desktop {
        manifest_args_full.push("-IncludeDesktop".to_string());
    }
```

**跳 7 · 执行(内核边界)。** Windows 与 Unix 分别走 PowerShell / bash。
这是本片与 `scripts/install.ps1`(片外)之间的**唯一接缝**:

`apps/bootstrap-installer/src-tauri/src/powershell.rs:284 @ 863e313`

```
    let mut cmd = Command::new(windows_powershell_exe());
    cmd.arg("-NoProfile");
    cmd.arg("-ExecutionPolicy").arg("Bypass");
    cmd.arg("-File").arg(script_path);
    for a in args {
        cmd.arg(a);
    }
    cmd
}
```

`apps/bootstrap-installer/src-tauri/src/powershell.rs:294 @ 863e313`

```
#[cfg(not(target_os = "windows"))]
fn build_command(script_path: &Path, args: &[String]) -> Command {
    // install.sh expects bash. /bin/bash is fine on macOS (Apple still
    // ships an old 3.2 bash; install.sh is written to that baseline).
    let mut cmd = Command::new("bash");
    cmd.arg(script_path);
    for a in args {
        cmd.arg(a);
    }
    cmd
}
```

**跳 8 · 解析结果帧。** 协议是「stdout 的**最后一行**能解析成含 `ok` + `stage` 的 JSON」。
倒着扫是因为 install.ps1 会在结果帧之前打一堆 banner:

`apps/bootstrap-installer/src-tauri/src/powershell.rs:365 @ 863e313`

```
pub fn parse_stage_result(stdout: &str) -> Option<crate::events::StageResultPayload> {
    for line in stdout.lines().rev() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
```

**跳 9 · 回到 UI。** 每一行 stdout 变成一个 `log` 事件,每次状态迁移变成一个 `stage` 事件,
推给 webview 的那一步:

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:913 @ 863e313`

```
    if let Err(e) = app.emit(BootstrapEvent::CHANNEL, &event) {
        tracing::warn!(?e, "failed to emit bootstrap event");
    }
```

store 的 listener 落到 `$bootstrap`,`apps/bootstrap-installer/src/routes/progress.tsx` 把
`stageOrder` 渲染成列表、给 running 的那一行挂 Loader。

**收尾(跳 10)** 全部 stage 成功后写原子标记,再把自己拷进 HERMES_HOME:

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:750 @ 863e313`

```
    let marker = match write_bootstrap_complete_marker(&install_root, &pin) {
```

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:770 @ 863e313`

```
    if let Err(err) = crate::paths::copy_self_to_hermes_home() {
```

随后 `Complete` 事件 → store 路由到 success → 用户点 `[ LAUNCH ]` → `launch_hermes_desktop`
→ `resolve_hermes_desktop_exe` 在 `apps/desktop/release/<os>-unpacked/` 里找**桌面打包产物**
—— 这一跳正好把本片的 A 块(安装器)与 B 块(桌面打包)接上:安装器最后要启动的东西,
就是 `npm run pack` 在用户机器上现产出来的那个目录。

---

## 4. 逐机制 / 逐区域

### 4.1 引导安装器为什么是 Rust + Tauri 而不是 Electron

模块注释自己交代了来历:

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:3 @ 863e313`

```
//! Direct port of `runBootstrap` from `apps/desktop/electron/bootstrap-runner.ts`.
```

取舍很清楚——第一次安装时机器上**还没有 Electron**,用 Electron 做引导器等于先下 150 MB
再下真程序;Rust + 系统 WebView(Windows 走 WebView2 `embedBootstrapper`)能压到 crate
自己写下的目标体积:

`apps/bootstrap-installer/src-tauri/Cargo.toml:74 @ 863e313`

```
# A 5-10MB signed installer is the goal. LTO + size-opt + single codegen unit.
```

代价是必须把 bootstrap-runner.ts 的行为**再实现一遍**,于是
`apps/bootstrap-installer/src-tauri/src/events.rs` 开头写着「1:1 mirror」、
`apps/bootstrap-installer/src-tauri/src/powershell.rs` 写着「Port of `spawnPowerShell`」
—— 这是一份**刻意维持的双份实现**,漂移风险由注释背书。

### 4.2 安装器 = 更新器:同一个二进制的两种模式

`AppMode::from_args` 只看有没有 `--update`;`force_setup_from_args` 另看 `--reinstall` / `--repair`,
而且**刻意与 mode 正交**,这条正交性由一条单测钉死。macOS 上还有第三种行为:
**bare 启动 + 已安装 = 不显示安装器,直接开 App**;为了这条路径不闪窗,窗口初始就是隐藏的,
由 `setup()` 决定显不显示 —— 这解释了 `/Applications/Hermes` 为什么既是安装器又是启动器。

| 关注点 | 锚点 + 摘录 |
|---|---|
| 模式解析 | `apps/bootstrap-installer/src-tauri/src/lib.rs:39`:`pub fn from_args<I, S>(args: I) -> Self` |
| 修复标志(与 mode 正交) | `apps/bootstrap-installer/src-tauri/src/lib.rs:58`:`pub fn force_setup_from_args<I, S>(args: I) -> bool` |
| 正交性由单测钉死 | `apps/bootstrap-installer/src-tauri/src/lib.rs:223`:`fn force_setup_flags_do_not_affect_mode_selection() {` |
| macOS 启动器快速路径 | `apps/bootstrap-installer/src-tauri/src/lib.rs:132`:`if cfg!(target_os = "macos") && mode == AppMode::Install && !force_setup {` |
| 为此窗口初始隐藏 | `apps/bootstrap-installer/src-tauri/tauri.conf.json:26`:`"visible": false` |

更新流程 `run_update` 的四段:

| 段 | 干什么 | 锚点 + 摘录 |
|---|---|---|
| 主流程 | 串起下面四段 | `apps/bootstrap-installer/src-tauri/src/update.rs:254`:`async fn run_update(app: AppHandle) -> Result<()> {` |
| 1 `handoff` | 等旧桌面释放 venv shim 与 `app.asar`(Windows 才有强制锁),超时就 `taskkill /F /T /IM hermes.exe` 并排除自身 PID | `apps/bootstrap-installer/src-tauri/src/update.rs:650`:`pub(crate) async fn wait_for_install_locks_free(install_root: &Path, app: &AppHandle, stage: &str) {` |
| 2 `update` | `hermes update --yes --gateway --force --branch <pin>`,失败自动**重试一次**(理由:更新跨越模块边界时第一次必然带着旧代码跑) | `apps/bootstrap-installer/src-tauri/src/update.rs:383`:`update_args.push("--force".into());` |
| 3 `rebuild` | `hermes desktop --build-only`,同样重试一次 | `apps/bootstrap-installer/src-tauri/src/update.rs:488`:`let rebuild_args: Vec<String> = vec!["desktop".into(), "--build-only".into()];` |
| 4 `install`(仅 macOS) | ditto 新 bundle → 三步换位(target→old,tmp→target,删 old)→ 去隔离属性 | `apps/bootstrap-installer/src-tauri/src/update.rs:1078`:`async fn swap_in_new_bundle(tmp: &Path, target: &Path, old: &Path) -> Result<()> {` |

`swap_in_new_bundle` 被单独抽出来正是为了能脱离 ditto 做单测,
三条 tokio 单测钉死了「任何失败路径都不能让 target 处于缺失状态」。

### 4.3 跨进程更新锁

`.hermes-update-in-progress` 这个文件被**三方**读写:Rust 更新器(`update.rs` 的 `UpdateMarkerGuard`)、
Electron(`apps/desktop/electron/update-marker.ts`)、Python(`hermes_cli/update_lock.py`)。
代码把 20 分钟的年龄上限写成常量并注明「三方读同一个文件,任何一方用更短的上限
都会偷走另外两方认为还活着的锁」。判活的豁免(不存在 / 解析失败 / pid 已死 / 超龄 /
**pid 就是自己**)写在 `live_marker_owner`;最后那条是 #74761:桌面会**抢先**用子进程 pid
写好标记,不豁免自己就会「自己拒绝自己」并无限重启。

| 关注点 | 锚点 + 摘录 |
|---|---|
| 20 分钟上限常量(三方共用) | `apps/bootstrap-installer/src-tauri/src/update.rs:129`:`const UPDATE_MARKER_MAX_AGE_SECS: u64 = 20 * 60;` |
| 判活与豁免入口 | `apps/bootstrap-installer/src-tauri/src/update.rs:148`:`fn live_marker_owner(path: &Path) -> Option<MarkerOwner> {` |
| 年龄计算 | `apps/bootstrap-installer/src-tauri/src/update.rs:157`:`let age_secs = now.saturating_sub(started_at);` |

### 4.4 打包链上每个脚本各自防的是哪一个具体故障

这一组脚本的共同气质:**每一个都是某次线上事故的疤**,注释里都点名了故障形态。

| 脚本 | 防的故障 |
|---|---|
| `assert-root-install.mjs` | 在 `apps/desktop` 里直接 `npm run dev` 而没在根 `npm ci`,vite 找不到 |
| `assert-dist-built.mjs` | 半成品 `dist/` 被打进包,应用启动后白屏 `ERR_FILE_NOT_FOUND` |
| `before-pack.mjs`(清目录) | 上一次 pack 被 Ctrl-C,unpacked 目录处于「有 Chromium 负载、缺 electron 主二进制」的半态,下一次 rename 报 ENOENT |
| `before-pack.mjs`(保留 .bak) | #69179:新 pack 产出的 Hermes.exe 装不起来时,更新器的完整性闸门能拿 `.bak` 回滚 |
| `before-pack.mjs`(重暂存 node-pty) | 跨 arch / 多 arch 打包时,`npm run build` 只暂存了宿主 arch 的原生模块 |
| `stage-native-deps.mjs` | 把错平台的 `.node` 打进包(靠魔数 fail-closed);macOS 的 `spawn-helper` 因为没有扩展名被按扩展名过滤掉 |
| `patch-electron-builder-mac-binary.mjs` | electron-builder 26.8.x 复制 Electron.app 时漏掉主二进制 |
| `run-electron-builder.mjs` | electron-builder 重新解包一份坏掉的 Electron.app(#38673 / #47917) |
| `set-exe-identity.mjs` + `after-pack.mjs` | 关掉 `signAndEditExecutable` 之后 exe 退回「Electron」图标与任务栏名;而只在 install.ps1 里补会漏掉更新路径 |
| `write-build-stamp.mjs` | 非 git 检出(ZIP 下载)时构建直接失败;全零 commit 让首启回落到分支引导 |

### 4.5 e2e 的两个非显然设计

**(a) 错误横幅是隐式断言。** `e2e/test.ts` 用 `addInitScript` 注入 MutationObserver 收集
所有 `[role="alert"]`,并在 `afterEach` 里**无条件**检查(即使用例已因别的原因失败),
理由是错误横幅常常**就是**根因,失败时压下去反而掩盖问题。
故意触发错误的用例得显式调 `allowErrorBanners()`。

**(b) 视觉回归只报告不失败。** `apps/desktop/e2e/visual-snapshot.ts` 没用 Playwright 的
`toHaveScreenshot`,而是自己把两张 PNG 交给 Electron 的 `nativeImage` 逐像素比,
超过 1% 才写出 `-expected/-diff` 并 `console.log`,**从不 throw**。
取舍很明确:像素级门禁在跨机器字体渲染下必然误报,于是把它降级成「CI 摘要里的一张图」。

| 关注点 | 锚点 + 摘录 |
|---|---|
| 错误横幅 afterEach 无条件触发 | `apps/desktop/e2e/test.ts:139`:`base.afterEach(async ({}, testInfo) => {` |
| 视觉差异 ≤1% 直接返回,超了也只 log | `apps/desktop/e2e/visual-snapshot.ts:141`:`if (comparison.mismatchRatio <= 0.01) {` |
| playwright 自己的 `toHaveScreenshot` 阈值(本片未用于门禁) | `apps/desktop/playwright.config.ts:53`:`toHaveScreenshot: {` |

### 4.6 perf 框架的隔离设计

`perf/README.md` 里最有迁移价值的一段是「为什么隔离重要」:跑着的 `hgui` 持有 Electron
单实例锁,第二个实例会立刻退出 —— 于是 `--spawn` 给自己配 `--user-data-dir`(独立锁作用域)、
独立 `HERMES_HOME`(独立后端与会话)、独立 `--remote-debugging-port`。
合成场景通过 `window.__PERF_DRIVE__` 直接驱动 `$messages`,**不花模型钱**。
这一条把「性能基准」从「需要真环境的手工活」变成了「CI 能跑的闸门」。

---

## 5. 文档与代码的出入

### ▲-1 README 声称 Windows 签名会自动发生,而构建配置关掉了这条路径

`apps/desktop/README.md:86 @ 863e313`

> Installers are built and uploaded to GitHub Releases manually. macOS/Windows signing & notarization happen automatically when the relevant credentials are present in the environment (`CSC_LINK` / `CSC_KEY_PASSWORD` / `APPLE_*` for macOS, `WIN_CSC_*` for Windows).

**整句一并判定**:这句话讲了三件事——(i) 安装器手工上传 Releases;(ii) macOS 侧凭据齐备即自动签名与公证;(iii) Windows 侧凭据齐备即自动签名。
(i) 无从证伪,不计。(ii) **成立**:`afterSign: scripts/notarize.mjs`,而该脚本正是
「`APPLE_API_KEY/_ID/_ISSUER` 齐备才做,缺了就跳过」:

`apps/desktop/scripts/notarize.mjs:79 @ 863e313`

```
  if (!rawApiKey || !keyId || !issuer) {
    console.log(
      'Skipping notarization: APPLE_API_KEY, APPLE_API_KEY_ID, and APPLE_API_ISSUER are not fully configured.'
    )
    return
  }
```

(iii) **被代码否定**:

`apps/desktop/package.json:248 @ 863e313`

```
    "win": {
      "legalTrademarks": "Hermes",
      "target": [
        "nsis",
        "msi"
      ],
      "signAndEditExecutable": false
    },
```

仓库自己在另一处解释了这个 flag 关掉了什么:

`apps/desktop/scripts/set-exe-identity.mjs:8 @ 863e313`

```
// apps/desktop/package.json sets build.win.signAndEditExecutable=false. That
// flag is load-bearing: turning electron-builder's own exe-editing ON also
// re-enables its signtool step, which fetches winCodeSign-2.6.0.7z, whose
// macOS symlinks crash 7-Zip on non-admin Windows (no Developer Mode = no
// SeCreateSymbolicLinkPrivilege). That is an unfixable dead end — we do NOT
// try to extract winCodeSign.
```

即:Windows 的 signtool 步骤是被**刻意**关掉的,`WIN_CSC_*` 在场也不会触发它;
仓库里也不存在任何替代的 Windows 签名脚本(搜索面:对
`apps/desktop/scripts/` 全目录 grep `signtool|WIN_CSC|osslsigncode|Set-AuthenticodeSignature`,
零命中;`notarize*.mjs` 两个脚本都以 `electronPlatformName !== 'darwin'` / `xcrun` 开头,仅 macOS)。
**归属标题**:该句在 `### Building installers` 之下,管辖的正是这几条 `dist:*` 命令。

### ▲-2 README 的 dev-sandbox 命令路径解析不到

`apps/desktop/README.md:71 @ 863e313`

> `../scripts/dev-sandbox.sh npm run dev`

该代码块紧跟在「`cd apps/desktop`」之后(README:63),所以 cwd 是 `apps/desktop`,
`../scripts/` 解析为 `apps/scripts/` —— 该目录不存在(`apps/` 下只有
`bootstrap-installer`、`desktop`、`shared`)。仓库里唯一的 `dev-sandbox.sh` 在仓库根 `scripts/`,
正确写法是 `../../scripts/dev-sandbox.sh`。

搜索面:`git ls-files | grep -i dev-sandbox`,全仓已跟踪文件,**1 条命中**:`scripts/dev-sandbox.sh`。

```verify
cd /home/user/hermes-agent && git ls-files | grep -i dev-sandbox
# scripts/dev-sandbox.sh
cd /home/user/hermes-agent && ls apps/desktop/../scripts/dev-sandbox.sh
# ls: cannot access '...': No such file or directory
```

### ▲-3 capabilities 的自述「不在 HERMES_HOME 之外写用户文件」被更新流程否定

`apps/bootstrap-installer/src-tauri/capabilities/default.json:4 @ 863e313`

> `"description": "Capabilities required by Hermes Setup. Narrowly scoped: we don't write user files outside HERMES_HOME, we don't read arbitrary paths, and the only external network call goes through reqwest (Rust side, not exposed to the webview).",`

这句同样讲三件事。第 2、3 件在 Rust 侧成立(唯一的 reqwest 调用点是 `install_script::download`;
crate 内没有任意路径读取)。第 1 件**不成立**:macOS 更新路径会把整个 `.app` 写到
`--target-app` 指向的位置(实践中是 `/Applications/Hermes.app`),那不在 HERMES_HOME 下。

`apps/bootstrap-installer/src-tauri/src/update.rs:1040 @ 863e313`

```
    let ditto = Command::new("/usr/bin/ditto")
        .arg(&rebuilt_app)
        .arg(&tmp)
        .current_dir(crate::paths::hermes_home())
        .status()
        .await
        .map_err(|e| anyhow!("running ditto: {e}"))?;
```

随后由下面两步把它 rename 到 `target_app` 并去掉隔离属性:

`apps/bootstrap-installer/src-tauri/src/update.rs:1057 @ 863e313`

```
    swap_in_new_bundle(&tmp, target_app, &old).await?;

    let _ = Command::new("/usr/bin/xattr")
        .arg("-dr")
        .arg("com.apple.quarantine")
        .arg(target_app)
        .current_dir(crate::paths::hermes_home())
        .status()
        .await;
```
*(注:这份 description 不在派工书列的六个文档源里,是 crate 内的自述;标 ▲ 时已注明来源。)*

### ▲-4 perf 入口注释说默认套件是 3 个场景,实际是 5 个

`apps/desktop/scripts/perf/run.mjs:5 @ 863e313`

```
// Default (no scenarios): runs the CI suite (stream, keystroke, transcript)
```

而默认套件的定义是「tier === 'ci' 的全部」:

`apps/desktop/scripts/perf/scenarios/index.mjs:36 @ 863e313`

```
/** Scenarios safe to run with no LLM credits / no live backend — the default suite. */
export const CI_SCENARIOS = Object.values(SCENARIOS)
  .filter(s => s.tier === 'ci')
```

§2.8 的机械枚举给出 5 个:`stream, keystroke, transcript, multitab, render-churn`。
`multitab` 与 `render-churn` 是后加的 ci 场景,注释没跟上。

### ◇-1 perf README 的场景表漏了两个真实场景

场景表从下面这一行开始,共 13 行:

`apps/desktop/scripts/perf/README.md:50 @ 863e313`

> | `stream` | ci | streaming longtasks, frame p95/p99, mutation cadence | measure-synthetic-stream, profile-synth-stream, profile-long-stream |

13 行里有一行是 `stream --real`(同一模块的一个 flag),故只覆盖 12 个模块;注册表里有 14 个。
**缺席的是 `multitab`(tier `ci`,在默认套件里,也在 baseline.json 里)与 `stream-history`(tier `manual`)。**
字面没有假陈述,属「代码有、文档无」。

### ◇-2 `Cargo.toml` 里 4 个依赖在整个 crate 中零引用

`once_cell`、`uuid`、`futures`、`thiserror` 在 `apps/bootstrap-installer/src-tauri/`
的任何 `.rs` 里都不出现。搜索面(含各自的常见使用形态,不只 `crate::`):

```verify
cd /home/user/hermes-agent/apps/bootstrap-installer/src-tauri && \
  grep -rnE "once_cell|OnceCell|Lazy|uuid|Uuid|futures|thiserror|derive\(Error" src/ build.rs ; \
  echo "exit=$?"
# (no output)
# exit=1
```

声明处(`futures` 单独在 `apps/bootstrap-installer/src-tauri/Cargo.toml:37`,其余三个连在一起):

`apps/bootstrap-installer/src-tauri/Cargo.toml:56 @ 863e313`

```
thiserror = "1"
once_cell = "1"
uuid = { version = "1", features = ["v4"] }
```

后果不是编译错误,而是**签名安装器的依赖树无谓变大 + 供应链面变宽**,配合 §6 ■-1 的
无 lockfile 更值得注意。

### ◎-1 「thin installer 不带 Python 负载」的说法保守但为真

`apps/desktop/scripts/test-desktop.mjs` 开头的注释说包里只有 Electron 壳 + extraResources。
`validateBundle()` 不但正向断言 `install-stamp.json` 与 node-pty 存在,还**反向断言**
旧的胖负载不得存在:

`apps/desktop/scripts/test-desktop.mjs:301 @ 863e313`

```
  const staleFactoryMarker = path.join(APP.resourcesPath, 'hermes-agent', 'hermes_cli', 'main.py')
  if (exists(staleFactoryMarker)) {
    die(
      `Thin-installer regression: factory-payload file should NOT be in the package: ${staleFactoryMarker}`
    )
  }
```

文档说的是「不带」,代码做的是「不带 + 每次打包都验证没带回来」—— 字面为真,实际更强。

---

## 6. 缺陷(■)

### ■-1(供应链,最重)引导安装器**不提交 Cargo.lock**,且**对下载的安装脚本零完整性校验**

两件事叠在一起才是问题的全貌。

**(a) Cargo.lock 被 gitignore。** 对一个**要被代码签名并分发给终端用户**的 bin crate,
Cargo 官方建议是提交 lockfile;这里反过来:

`apps/bootstrap-installer/.gitignore:3 @ 863e313` —— 该行内容为 `/src-tauri/Cargo.lock`。

```verify
cd /home/user/hermes-agent && git ls-files apps/bootstrap-installer | grep -i cargo
# apps/bootstrap-installer/src-tauri/Cargo.toml     ← 只有 Cargo.toml,没有 Cargo.lock
cd /home/user/hermes-agent && git check-ignore -v apps/bootstrap-installer/src-tauri/Cargo.lock
# apps/bootstrap-installer/.gitignore:3	apps/bootstrap-installer/src-tauri/Cargo.lock
```

配合 `Cargo.toml` 里全部是宽松 caret 约束(`tauri = "2"`、`tokio = "1"`、`reqwest = "0.12"`、
`serde = "1"`…),**同一个 commit 在两天里构建出的安装器,依赖树可以不同,且 diff 里看不出来**。

**(b) 下载下来的 install 脚本不做任何校验就执行。** 搜索面:对
`apps/bootstrap-installer/src-tauri/` 全目录(含 build.rs、Cargo.toml、tauri.conf.json)
grep `sha256|sha1|checksum|digest|minisign|gpg|signature|integrity`(大小写不敏感),
**唯一命中在二进制文件 `icons/icon.icns` 内部**,`.rs` / `.toml` / `.json` 零命中:

```verify
cd /home/user/hermes-agent && grep -rniE \
  "sha256|sha1|checksum|digest|minisign|gpg|signature|integrity" \
  apps/bootstrap-installer/src-tauri/
# grep: apps/bootstrap-installer/src-tauri/icons/icon.icns: binary file matches
```

也就是说信任链**完全等于 TLS + GitHub**:`download()` 拿到 200 就落盘(§3 跳 5 的块),
然后 `-ExecutionPolicy Bypass -File` 执行(§3 跳 7 的块)。
默认构建**连 commit pin 都没有**(见 §3 跳 4 里 `build.rs` 的逐字块:commit pin 是 opt-in),
所以出厂默认是**跟分支 HEAD 走**,每次安装取当时的 `main`。

**(c) 唯一一处叫 `verify` 的代码做的是相反的事。** 安装器把自己拷进 HERMES_HOME 后,
在 macOS 上会先剥掉隔离属性,再验签;**验签失败就 ad-hoc 自签**:

`apps/bootstrap-installer/src-tauri/src/paths.rs:142 @ 863e313`

```
    let verify = Command::new("/usr/bin/codesign")
        .arg("--verify")
        .arg(path)
        .status();

    if !matches!(verify, Ok(status) if status.success()) {
        let _ = Command::new("/usr/bin/codesign")
            .args(["--force", "--sign", "-"])
            .arg(path)
            .status();
    }
```

`codesign --force --sign -` 是**用「-」这个 ad-hoc 身份重签**。它让一个签名坏掉的
helper 仍然能被 LaunchServices 拉起 —— 也就是把「签名坏了」这个信号消掉。
桌面之后会用这个文件做 in-app 更新(注释自述)。

### ■-2 release profile 是 `panic = "abort"`,但更新锁的文档保证依赖 unwind

`apps/bootstrap-installer/src-tauri/Cargo.toml:73 @ 863e313`

```
[profile.release]
# A 5-10MB signed installer is the goal. LTO + size-opt + single codegen unit.
panic = "abort"
codegen-units = 1
lto = true
opt-level = "s"
strip = true
```

`apps/bootstrap-installer/src-tauri/src/update.rs:104 @ 863e313`

```
/// its `Drop` removes the marker on EVERY exit path — success, early
/// `return Err`, or a panic that unwinds through `run_update` — so a crashed
/// or aborted updater can never permanently strand the marker and block
```

`panic = "abort"` 下**不会 unwind**,`Drop` 不会跑,标记会留在盘上。
实际影响被两道兜底缩小了(20 分钟年龄上限 + pid 判活,见 §4.3 表),
但注释声称的不变量「EVERY exit path」在 release 构建里不成立;
`Drop` 只在 success / early-return 两条路上有效。
*(在 debug 构建里成立,单测 `update_marker_guard_writes_then_removes_on_drop` 因此是绿的
—— 这正是这类缺陷难被测试抓住的原因:测试跑在 dev profile。)*

### ■-3 `--target-app` 只校验后缀,不校验位置

`apps/bootstrap-installer/src-tauri/src/update.rs:962 @ 863e313`

```
    arg_value_from_args(args, "--target-app")
        .map(PathBuf::from)
        .filter(|p| p.extension().and_then(|e| e.to_str()) == Some("app"))
```

任何以 `.app` 结尾的路径都会被接受,随后 `swap_in_new_bundle` 会把它 rename 到
`<path>.hermes-update-old` 再把 Hermes 放进去,最后 `xattr -dr com.apple.quarantine`。
调用者是桌面(可信),所以这不是远程可利用,但**没有任何「必须在 /Applications 或用户
Applications 下」的约束**;一次参数拼接错误就会移走一个无关的 `.app`。
对比 `install_macos_app_update` 开头那句拒绝语:

`apps/bootstrap-installer/src-tauri/src/update.rs:992 @ 863e313`

```
            "refusing to install update into non-app path: {}",
```

—— 校验意图是有的,只是止步于扩展名。

### ■-4 两个直接依赖在**全仓任何 package.json 里都没声明**

`apps/desktop/scripts/test-desktop.mjs:6 @ 863e313`

```
import { listPackage } from '@electron/asar'
```

`ws` 同理,被 `diag-overlay-ab.mjs` / `diag-overlay-churn.mjs` / `diag-overlay-full.mjs` /
`diag-overlay-sweep.mjs` 四个脚本 `import WebSocket from 'ws'`。

搜索面:仓库里 **git 跟踪的全部 11 个 `package.json`**,四类依赖字段
(`dependencies` / `devDependencies` / `peerDependencies` / `optionalDependencies`)全查:

```verify
cd /home/user/hermes-agent && for f in $(git ls-files '*package.json' | grep -v node_modules); do
python3 - "$f" <<'PY'
import json,sys
p=sys.argv[1]
try: d=json.load(open(p))
except Exception: sys.exit()
for k in ('dependencies','devDependencies','peerDependencies','optionalDependencies'):
    for n in ('@electron/asar','ws'):
        if n in d.get(k,{}): print(f"{p}: {k}.{n} = {d[k][n]}")
PY
done; echo "(no lines above = zero declarations)"
```

两者都只能靠 npm 把 electron-builder 的传递依赖**提升**到根 `node_modules` 才解析得到。
`npm run check` → `test:desktop:all` → `test-desktop.mjs` 落在这条链上,所以这不是
「只影响诊断脚本」:一次 electron-builder 升级把 `@electron/asar` 变成嵌套依赖,`check` 就崩。

### ■-5 `e2e/fixtures.ts` 把同一个 interface 声明了两次

`apps/desktop/e2e/fixtures.ts:357 @ 863e313`

```
export interface MockBackendOptions {
```

`apps/desktop/e2e/fixtures.ts:377 @ 863e313`

```
export interface MockBackendOptions {
```

第二处顶着一段本该属于 `setupMockBackend` 的 JSDoc(「Set up a full mock-backend E2E environment…」),
显然是插入位置错了。TypeScript 的 interface 声明合并让它**不报错**,四个字段全部可用,
所以这个错误只会以「文档注释挂在错误的东西上」的形式存在 —— 读者按注释找函数会找到一个 interface。

### ■-6 两个 diag 脚本硬编码了作者机器的 devtools page id

`apps/desktop/scripts/diag-overlay-full.mjs:7 @ 863e313`

```
const WS_URL = 'ws://127.0.0.1:9222/devtools/page/6E095DBE024BD280C674D00023C01201'
```

同目录的 sweep 版是同一个常量,但至少给了 `process.env.CDP_WS` 覆盖口:

`apps/desktop/scripts/diag-overlay-sweep.mjs:6 @ 863e313`

```
const WS_URL = process.env.CDP_WS || 'ws://127.0.0.1:9222/devtools/page/6E095DBE024BD280C674D00023C01201'
```

`diag-overlay-full.mjs` 没有任何覆盖口,在别人机器上必然连不上。
而同目录里的其它探针都用动态 target 发现,说明正确写法就在旁边:

`apps/desktop/scripts/probe-renderer.mjs:2 @ 863e313`

```
const list = await (await fetch('http://127.0.0.1:9222/json/list')).json()
```

### ■-7 `probe-model-picker.mjs` 的自述用法路径是错的

`apps/desktop/scripts/probe-model-picker.mjs:4 @ 863e313`

```
//   node scripts/perf/probe-model-picker.mjs [--port 9222] [--rounds 5]
```

文件实际在 `apps/desktop/scripts/probe-model-picker.mjs`(不在 `perf/` 下),
它的 import 也写的是 `'./perf/lib/cdp.mjs'`(:5),与 `scripts/` 位置一致。
即**代码位置对、用法说明错**,照抄用法必然 MODULE_NOT_FOUND。

### ■-8 `rebuild-native.mjs` 无人引用

搜索面:`apps/desktop/package.json` 的 51 条 script(§2.1 全表,无 `rebuild-native`)
+ 对整个 `apps/desktop/` 递归 grep `rebuild-native` 与 `rebuildNodePty`:

```verify
cd /home/user/hermes-agent && grep -rn "rebuild-native\|rebuildNodePty" apps/ --include='*.mjs' \
  --include='*.json' --include='*.ts' --include='*.tsx'
# apps/desktop/scripts/rebuild-native.mjs:9:export async function rebuildNodePty({ arch = process.arch } = {}) {
# apps/desktop/scripts/rebuild-native.mjs:21:  await rebuildNodePty({ arch })
```

只有它自己。真正需要重编时走的是另一条路 —— 直接 spawn `electron-rebuild`:

`apps/desktop/scripts/stage-native-deps.mjs:316 @ 863e313`

```
    const rebuildArgs = [
      '../../node_modules/.bin/electron-rebuild',
      '-f',
      '-w',
      'node-pty',
      '--arch',
      arch
    ]
```

两条重编路径并存,其中一条是死的。

### ■-9 `get_bootstrap_status` 注册了但前端从不调用

`BootstrapHandle` 的注释说这个状态是「让前端在窗口刷新后重新查询」用的,
但 `apps/bootstrap-installer/src/store.ts` 里 6 个 action 无一调用它(§2.4 表);
另一处注释也直接承认 UI 不会轮询它:

`apps/bootstrap-installer/src-tauri/src/bootstrap.rs:748 @ 863e313`

```
    // Marker publish is terminal for this run: a write failure must emit Failed
    // so the UI leaves the progress state (it does not poll get_bootstrap_status).
```

即:**设计意图(刷新后可恢复)没有落地**,窗口一刷新前端就回到 `welcome` 且丢掉全部进度。
搜索面:`apps/bootstrap-installer/src/` 全目录 grep `get_bootstrap_status`,零命中。

### ■-10 `mock-server.ts` 的剧本计数器是**模块级全局**,注释却称「per-server」

`apps/desktop/e2e/mock-server.ts:105 @ 863e313`

```
/** Per-server request counter so we can walk through the script turns. */
let _scriptIndex = 0
```

`_scriptIndex` 与其后 5 个同类计数器都在模块顶层,`startMockServer()` 每次调用**不重置**它们
(重置要显式调 `restartMockServer()`,:764)。同一个 worker 进程里先后起两个 mock server
(如 `interim-messages.spec.ts` 的两个 describe)会共享同一份游标。当前靠
`fullyParallel: false` + serial describe + 手动 `restartMockServer()` 避开,
但这是**约定而非机制**,而注释把它描述成了机制。

### ■-11 `assert-dist-built.mjs` 的注释描述了一个不存在的 build 步骤

`apps/desktop/scripts/assert-dist-built.mjs:4 @ 863e313`

```
// If the `build` step (tsc -b && vite build) fails but packaging proceeds
```

`build` 里没有 `tsc -b`(§2.1 第 14 条的逐字块)。同段还写「a stale checkout that fails
typecheck」—— 由于 `build` 不做类型检查,这个场景根本到不了这里。
同类的还有下面这句提到 `electron-main.cjs`,而 `apps/desktop/scripts/bundle-electron-main.mjs`
产出的是 `dist/electron-main.mjs`:

`apps/desktop/scripts/test-desktop.mjs:87 @ 863e313`

```
// Match node-pty native binding location to what the bundled electron-main.cjs
```

---

## 7. 测试(行为规格)

### 7.1 本片能跑的:`scripts/**.test.mjs`(4 文件)

```verify
# 通用形式:在任意已 `npm ci`(仓库根)的 hermes-agent 检出里执行 ——
cd apps/desktop && npx vitest run --project electron scripts/
# 本轮实测用的是主线备好的、基线之外的副本(避免在只读基线里产生 node 侧产物):
#   cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project electron scripts/
```

**passed 37 / failed 0 / skipped 0**,4 个测试文件全部执行(无整文件跳过、无零执行)。
覆盖的 4 个模块:`assert-dist-built` / `before-pack` / `stage-native-deps` / `write-build-stamp`。

作为对照,整个 `electron` project(含片外的 `electron/**`,74 个文件):

```verify
cd apps/desktop && npx vitest run --project electron
# Test Files  78 passed | 1 skipped (79)
#      Tests  938 passed | 2 skipped (940)
```

**skipped 逐个点名(均在片外,列出以免汇总里被当成通过)**:
- `apps/desktop/electron/windows-remote-live.test.ts` —— **整文件跳过**,掩盖 1 个用例
  (`live Windows remote lifecycle spawns, authenticates, reuses, and cleans exact ownership`);
- `apps/desktop/electron/fs-read-dir.test.ts` —— 单用例跳过 1 个
  (`readDirForIpc marks a Windows junction to a directory as a directory`,原因 `junctions are a Windows-specific symlink type`)。

环境记录:node 环境为主线在 `/home/user/r10b-ts/hermes-agent` 备好的 `git archive` 副本,
vitest 4.1.10;**本片未安装任何包**。

### 7.2 本片跑不了的:`e2e/` 25 文件(如实申报)

**19 个 spec / 47 个用例一个都没跑。** 原因是真 Electron 二进制不存在 —— `findElectron()`
先找仓库根的 `node_modules/electron/dist/electron`,找不到再 `which electron`,两者皆无就抛:

`apps/desktop/e2e/fixtures.ts:290 @ 863e313`

```
  const localElectron = path.join(REPO_ROOT, 'node_modules', 'electron', 'dist', 'electron')
```

主线已确认本容器的 node 环境是用 `ELECTRON_SKIP_BINARY_DOWNLOAD=1` 装的。
另外 `test:e2e` 的第一步是 `npm run build`(含 `vite build` + esbuild + 暂存 node-pty),
`launch-packaged-app.spec.ts` 还要求先 `npm run pack`(完整 electron-builder 打包)。

**因此本底稿对 e2e 的一切结论都来自读源码,不来自运行。**
凡涉及「这些用例证明了什么行为」的地方,我写的是「用例断言了 X」,不是「X 已被验证」。

### 7.3 Rust 单测(未跑)

`apps/bootstrap-installer/src-tauri/src/` 里有 **51 个 `#[test]` / `#[tokio::test]`**
(lib.rs 5、bootstrap.rs 5、install_script.rs 8、powershell.rs 9、update.rs 24),
需要 `cargo test`。容器内无 Rust 工具链、且跑 cargo 会在基线里生成 `target/`(违反只读铁律),
故**未运行**。这些用例作为行为规格被本底稿引用时,均标注为「用例断言」。

**待提供项**:
- Electron 二进制(或允许 `npm i electron` 下载)+ 一次 `npm run build`,才能跑 19 个 e2e spec;
- 再加一次 `npm run pack`,才能跑 `launch-packaged-app.spec.ts` 的 4 个;
- Rust 工具链 + **在基线之外的副本里** `cargo test`,才能跑安装器的 51 个单测;
- macOS 主机 + Apple 凭据(`APPLE_API_KEY/_ID/_ISSUER` 或 `APPLE_NOTARY_PROFILE`),
  才能验证 `notarize.mjs` / `notarize-artifact.mjs`;Windows 主机才能验证 rcedit 与 NSIS 路径。

---

## 8. 判据自查

| # | 判据 | 自评 |
|---|---|---|
| 1 | 点名到位 | **达标**。149 个文件全部以全路径出现在 §0 的四张表里,逐个带一句话角色;同型薄文件(16 个 diag-*、15 个 perf 场景、19 个 spec)也是**逐个列全路径**,没有「等 N 个」写法。 |
| 2 | 接缝穷举 | **达标**。9 张表:desktop 51 条 npm script(全)、installer 12 条(全)、打包产物矩阵(3 平台 × target + 4 钩子 + 内容面)、Tauri 命令 9 条(全,附定义处与前端调用点)、事件通道 1 + 变体 5(全)+ store 的 6 action / 5 atom(全)、Tauri 权限 9 条(全)+ CSP、e2e 19 spec / 47 用例(全)+ mock 触发词 8 条(全)、perf 场景 14 个(全)+ tier 分布、构建脚本导出面(全)。每张表都给了可重跑的枚举命令与条数。 |
| 3 | 端到端链 | **达标**。§3「点 `[ INSTALL ]` → 第一个 stage 跑起来」共 10 跳,每跳一个锚点 + 逐字块,终点接回 §0.B 的桌面打包产物。 |
| 4 | 逐字取证 | **达标**。逐字围栏块 20+ 个(rust/toml/json/mjs/ts 均有),远超 2 个下限。 |
| 5 | 记号 | **达标**。▲×4、◇×2、◎×1、■×11,每条带锚点;全称否定处均写出搜索面。 |

**引用关卡自测(交付前跑过,主线复核用):**

```console
python3 scripts/verify_citations.py /home/user/hermes-agent notes/r10b-raw-build-package.md
citations=55  OK=52  UNCHECKED=3
可校验比例 OK/55 = 94.5%
table_anchors=45  OK=43  UNCHECKED=2
OK: every code-block-backed citation matches the baseline
```

0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE;可校验比例 94.5%(下限 70%)。
片内 149 个文件的**全路径**均在本文出现(机械核对:逐条 `in` 匹配,缺失 0)。

**未达标 / 需打折的地方,如实写出:**
- **e2e 只读不跑**(§7.2)。19 个 spec 的行为我只能转述其断言,不能声称验证过。
- **Rust 51 个单测未跑**(§7.3)。
- **perf 框架的 14 个场景我读了注册面与 tier,没有逐个读实现体**——这符合 L2「读接口面不读实现体」,
  但要说明:场景的 `metrics` 字段名我没有逐个枚举(那属于实现体)。
- **diag-* 16 个脚本按 L3 深度处理**(读头部意图 + 抽查关键常量),没有逐行读。它们是一次性调查工具,不构成对外接缝。
- `apps/desktop/preview-demo.html`、`components.json`、`.gitignore` 三个只确认了用途,未细读。

---

## 9. 移交项

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议下一轮做什么 |
|---|---|---|---|
| H-K-a | `apps/bootstrap-installer/.gitignore:3`:`/src-tauri/Cargo.lock` | 签名分发的 bin crate 不提交 lockfile,依赖树不可复现 | 与片外 `scripts/install.ps1` / `install.sh` 的下载校验一并评估整条供应链;确认 CI 是否在别处固定了依赖 |
| H-K-b | `apps/bootstrap-installer/src-tauri/src/install_script.rs:326`:`"https://raw.githubusercontent.com/NousResearch/hermes-agent/{}/scripts/{}",` | 下载即执行,无校验和/签名;默认构建连 commit pin 都没有 | 追 `scripts/install.ps1` 自身:它 clone 仓库时是否验签、是否 pin;这决定整条链的信任根 |
| H-K-c | `apps/bootstrap-installer/src-tauri/Cargo.toml:75`:`panic = "abort"` | release 下 `Drop` 不跑,`UpdateMarkerGuard` 注释宣称的「EVERY exit path」不成立 | 交叉验证 `hermes_cli/update_lock.py` 与 `apps/desktop/electron/update-marker.ts` 的兜底是否足以覆盖 |
| H-K-d | `apps/desktop/scripts/test-desktop.mjs:6`:`import { listPackage } from '@electron/asar'` | 全仓 11 个 package.json 均未声明该依赖,靠 npm 提升解析;它在 `npm run check` 链路上 | 查 CI 工作流是否真的跑 `npm run check`;若跑,这是一颗定时炸弹 |
| H-K-e | `apps/desktop/e2e/tile-unread-bug.spec.ts:166`:`test.describe.skip('sidebar states — split (visible) unread bug (RED)', () => {` | 一个已知 UI 缺陷被写成红灯用例后整块跳过 | 交给做渲染器/侧栏那一片:该 bug 是否已在别处修掉、这块 skip 是否可以拆 |
| H-K-f | `apps/bootstrap-installer/src-tauri/src/update.rs:957`:`fn target_app_from_args<I, S>(args: I) -> Option<PathBuf>` | `--target-app` 只校验 `.app` 后缀、不校验位置,随后会被 rename 并覆写 | 查桌面侧(`apps/desktop/electron/`)是谁拼这个参数、拼的是什么 |
| H-K-g | `apps/bootstrap-installer/src-tauri/src/bootstrap.rs:139`:`pub async fn get_bootstrap_status(` | 命令已注册,前端 0 调用,「刷新后可恢复」的设计没落地 | 若后续要讲「安装器的可恢复性」,注意别照抄注释里的意图 |
| H-K-h | `apps/desktop/scripts/perf/scenarios/index.mjs:37`:`export const CI_SCENARIOS = Object.values(SCENARIOS)` | `perf/README.md:46` 起的场景表 13 行只覆盖 12 个模块,漏了 `multitab`(ci,在默认套件与 baseline 里)与 `stream-history`(manual) | 写成品章讲 perf 框架时以注册表为准,不要照抄 README 的表 |

---

## 10. 本片成本自报

```text
片号            : K
层              : L2
文件数 / 行数   : 149 / 22,551
实际打开的文件数: 61
                  (完整读:bootstrap-installer 全部 8 个 .rs + build.rs + Cargo.toml +
                   tauri.conf.json + capabilities + manifest + store.ts + 4 个 route/component 头部;
                   desktop 的 package.json / vite / vitest / playwright / 3 个 tsconfig /
                   eslint / index.html / AGENTS.md / DESIGN.md / README.md;
                   scripts 的 11 个打包主链 + 3 个签名 + test-desktop + perf/README + run.mjs +
                   scenarios/index.mjs;e2e 的 test.ts / fixtures.ts / mock-server.ts /
                   visual-snapshot.ts / fix-electron-tracing.ts。
                   另有 ~40 个文件只读了头部注释 + grep 出的关键常量,不计入。)
实际读过的行数  : 约 12,000
                  (估法:完整读的 61 个文件按其真实行数累加约 11,200;头部+抽查的 ~40 个
                   文件按每个 20 行计约 800。占全片 22,551 行的 ~53%。)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈是**三种不同技术栈的接缝要各自穷举**——Rust/Tauri 的命令与
                  权限面、npm/electron-builder 的脚本与钩子链、Playwright 的夹具与剧本面,
                  三者没有共同的枚举方式,每张表都要单独想「怎么机械数」。
                  单文件长度不是瓶颈(最长 1,641 行的 update.rs 结构清晰);
                  真正花时间的是**跨栈追链**(§3 那 10 跳跨了 TS→Rust→shell 三层)
                  与**否定性结论的搜索面**(§6 的 ■-1/■-4/■-8 各需要一次全仓级枚举)。
```
