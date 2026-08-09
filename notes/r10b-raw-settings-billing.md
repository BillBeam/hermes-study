# r10b 片C · 设置面、计费与 profile / 网关设置 —— 底稿

> 层:**L2**(读接口面,不读实现体;接口面**不抽样**)。
> 范围:`data/r10b/slices/C.txt`,**77 文件 / 19,070 行**,全部在 `/home/user/hermes-agent/` 下。
> 溯源约定:凡对 hermes-agent 行为的断言,锚点写作 `路径:行号 @ 863e313`,**单独成行、置于代码块之前**。
> 本片探针:`data/r10b/probes/probe_c_config_keys.py`、`probe_c_seams.py`、
> `probe_c_bridge_and_shared.py`、`probe_c_billing_codes.py`、`probe_c_i18n.py`。

---

## 0. 本片范围与逐文件点名(判据 1)

77 个文件分七组。**每个文件都写全路径**;同型薄文件归组叙述,组内仍逐个列出。

### 0.1 `apps/desktop/src/app/gateway/hooks/` —— 主网关连接的生命周期(3 文件 / 842 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/app/gateway/hooks/use-gateway-boot.ts` | 638 | 主 socket 的**唯一** boot / 重连 / 软切换机器:冷启动握手、睡眠唤醒重连(全抖动退避 + 45s 升级为可恢复错误)、profile 采纳、后台 profile socket 的保活与剪枝、HMR 存活移交、卸载清理 |
| `apps/desktop/src/app/gateway/hooks/use-gateway-request.ts` | 148 | 出站 RPC 的统一入口 `requestGateway`:失败时按 `not connected|connection closed` 判定并做一次自愈重连(主 profile 走 OAuth 重铸票据,后台 profile 交给 registry),把 reauth 错误顶替掉不可行动的传输错误 |
| `apps/desktop/src/app/gateway/hooks/gateway-hmr-survivor.ts` | 56 | 开发期 HMR 存活槽:`Symbol.for` 键挂 globalThis,一次性取出,`import.meta.hot` 缺席时整模块被摇树掉,生产环境零影响 |

### 0.2 `apps/desktop/src/app/profiles/` —— profile 管理覆盖层(4 文件 / 748 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/app/profiles/index.tsx` | 388 | Profiles 覆盖层主视图:左列表 + 右详情(名称/路径/model/skill 数)+ 内嵌 `SOUL.md` 编辑器(CodeEditor,脏标记 + 保存) |
| `apps/desktop/src/app/profiles/create-profile-dialog.tsx` | 166 | 新建 profile 对话框;导出 `isValidProfileName`(`/^[a-z0-9][a-z0-9_-]{0,63}$/`),支持 clone_from 与可选 SOUL |
| `apps/desktop/src/app/profiles/rename-profile-dialog.tsx` | 129 | 重命名对话框,复用上面的名字校验;同名即无操作关闭 |
| `apps/desktop/src/app/profiles/delete-profile-dialog.tsx` | 65 | 删除确认;若删的是**当前活跃 profile**,在宿主刷新之后再把网关/侧栏切回 `default`(顺序是有意的,防止 refreshActiveProfile 竞态把 pill 打回去) |

### 0.3 `apps/desktop/src/app/settings/` 骨架与共享件(11 文件 / 2,335 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/app/settings/index.tsx` | 342 | 设置覆盖层的**路由与导航面**:`SETTINGS_VIEWS`(17 项)、`?tab=` 主视图 + `?pview=/?kview=` 子视图、`?tab=mcp` 老书签重定向到 Capabilities、导出/导入/重置 config 的页脚 |
| `apps/desktop/src/app/settings/constants.ts` | 794 | 设置面的**数据表**:`PROVIDER_GROUPS`(31 条 env 前缀→厂商卡)、`BUILTIN_PERSONALITIES`(14)、`ENUM_OPTIONS`(21 键的下拉选项)、`FREE_INPUT_KEYS`(17)、`FIELD_LABELS`/`FIELD_DESCRIPTIONS`、`SECTIONS`(8 段 96 键)、`MODE_OPTIONS` |
| `apps/desktop/src/app/settings/helpers.ts` | 319 | 纯函数层:`getNested`/`setNested`(带原型污染防护)、`sectionFieldEntries`、`enumOptionsFor`、`providerGroup`(最长前缀匹配)、`redactedValue`、`isExternalMemoryProvider`、TTS/STT 自定义 command provider 枚举 |
| `apps/desktop/src/app/settings/types.ts` | 52 | 片内类型:`SettingsView` 联合、`SettingsPageProps`、`DesktopConfigSection`、`EnvRowProps` |
| `apps/desktop/src/app/settings/primitives.tsx` | 244 | 布局原语:`SettingsContent`/`SectionHeading`/`SettingsSection`/`ListRow`/`ToggleRow`/`Pill`/`NavLink` + 三个骨架屏组件;`EmptyState` 转出 |
| `apps/desktop/src/app/settings/config-field.tsx` | 235 | **一行配置的通用渲染器**:按 schema.type + 键名派发到 Switch / SearchableSelect / ComboboxInput / Select / number Input / list Input / JSON Textarea / Textarea / Input |
| `apps/desktop/src/app/settings/config-settings.tsx` | 432 | 通用 config 段容器:草稿态 + 550ms 防抖自动保存 + profile 切换时丢弃草稿;`voiceFieldVisible` 只显示选中 provider 的子字段;`AttachmentSizeSetting`(设备本地 MB 上限) |
| `apps/desktop/src/app/settings/field-copy.ts` | 57 | schema 键(snake)↔ 文案键(camel)互转 + `defineFieldCopy` 树展平(重复键直接抛错) |
| `apps/desktop/src/app/settings/combobox-input.tsx` | 114 | 开放世界字段(音色/模型名)的自由输入 combobox,取代原生 `<datalist>` |
| `apps/desktop/src/app/settings/searchable-select.tsx` | 115 | 大闭集(约 590 个 IANA 时区)的可搜索 Select;导出 `rankSearchOption`(末段优先打分) |
| `apps/desktop/src/app/settings/use-deep-link-highlight.ts` | 80 | 深链高亮通用 hook:轮询等目标行挂载 → 滚动 + 闪烁 → 成功后才删 query 参数 |

### 0.4 `apps/desktop/src/app/settings/` 各设置面板(21 文件 / 6,169 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/app/settings/gateway-settings.tsx` | 1521 | **最大的一个面板**:四种连接模式(local/cloud/remote/ssh)、per-profile scope chip、远端 URL 探测→OAuth 或 token 控件二选一、Hermes Cloud 门户登录 + 多组织选择 + agent 发现与静默级联、SSH 主机建议/解析/连通性测试、七类 sshError 文案 |
| `apps/desktop/src/app/settings/model-settings.tsx` | 1280 | 主模型 provider/model 选择与应用、`agent.reasoning_effort`/`agent.service_tier` 默认值、8 个辅助任务槽位(`AUX_TASKS`)、MoA preset 编辑、粘贴 API key 即时激活 provider |
| `apps/desktop/src/app/settings/toolset-config-panel.tsx` | 880 | Capabilities 侧的 toolset 后端配置面(被设置面共用):provider 行 + 就绪度 pill、env key 字段(**含明文回显**)、post-setup 安装器与日志、Nous Portal device-code 登录、模型目录选择、web 的 search/extract 分能力指派 |
| `apps/desktop/src/app/settings/appearance-settings.tsx` | 549 | 外观页:语言、主题网格 + VS Code Marketplace 实时搜索安装、UI 缩放、终端字体、半透明、背景、表情回应、工具视图、嵌入同意;末尾挂 `PetSettings` |
| `apps/desktop/src/app/settings/providers-settings.tsx` | 526 | Providers 页三个子视图:OAuth 账号选择器(与首启 onboarding 同组件)、API key 分组卡、自定义端点;`buildProviderKeyGroups` 用后端 provider 标签优先、前缀猜测兜底 |
| `apps/desktop/src/app/settings/pet-settings.tsx` | 403 | 宠物画廊(网关 RPC 驱动)+ 启用/缩放/漫游开关,是 Appearance 的一节 |
| `apps/desktop/src/app/settings/custom-endpoints-settings.tsx` | 403 | 自定义 OpenAI 兼容端点的 CRUD + 连通性测试 + 模型发现 + 设为默认 |
| `apps/desktop/src/app/settings/sessions-settings.tsx` | 391 | 归档会话列表(恢复/永久删除)+ `sessions.auto_archive[_days]` 配置 + 默认项目目录(走 Electron `settings.*` 桥) |
| `apps/desktop/src/app/settings/keybind-settings.tsx` | 276 | 键位表:分类折叠、搜索、冲突提示、单条重置与全量重置;只读快捷键单列 |
| `apps/desktop/src/app/settings/computer-use-panel.tsx` | 240 | Computer Use 预检卡:macOS 两项 TCC 授权行 + 非 macOS 的驱动健康;授权走 spawn-action 轮询 |
| `apps/desktop/src/app/settings/env-credentials.tsx` | 199 | 凭据面的**共享数据层** `useEnvCredentials`:一次 `getEnvVars`,再提供 save/clear/reveal 与本地乐观打补丁;另导出 `filterEnv`、`SettingsCategoryHeading` |
| `apps/desktop/src/app/settings/uninstall-section.tsx` | 186 | About 页底部危险区:三档卸载(gui / lite / full),按是否装了 agent 过滤可见项 |
| `apps/desktop/src/app/settings/about-settings.tsx` | 183 | 版本、更新检查/应用、发行说明外链、分支+SHA 提示,挂 `UninstallSection` |
| `apps/desktop/src/app/settings/env-var-actions-menu.tsx` | 179 | 一个 env 变量行的动作集(docs / 明文回显 / 编辑 / 去 Keys 页管理 / 清除),下拉菜单与右键菜单共用同一份 items |
| `apps/desktop/src/app/settings/fallback-models-field.tsx` | 170 | `fallback_providers`(`{provider,model}` 列表)的结构化编辑器,替代会渲染成 `[object Object]` 的通用 list 输入 |
| `apps/desktop/src/app/settings/terminal-font-setting.tsx` | 169 | `terminal.font_family` 单键编辑 + 实时预览 + profile 切换时的种子/回滚机器 |
| `apps/desktop/src/app/settings/terminal-backend-panel.tsx` | 160 | 终端执行后端选择器(带健康探针),是 `terminal.backend` 枚举的 Capabilities 版 |
| `apps/desktop/src/app/settings/voice-provider-fields.tsx` | 141 | 从 `SECTIONS` 的 voice 段派生某个 TTS/STT provider 的子字段,内嵌进 toolset 面板,与 Settings→Voice 同一套渲染与自动保存 |
| `apps/desktop/src/app/settings/plugins-settings.tsx` | 132 | 桌面端插件列表(disk/runtime/bundled 排序)、启停开关、打开插件目录、重扫 |
| `apps/desktop/src/app/settings/notifications-settings.tsx` | 119 | 原生通知总开关 + 分类开关 + 完成音变体选择 + 发送测试通知 |
| `apps/desktop/src/app/settings/quick-entry-settings.tsx` | 103 | 全局呼出快捷键设置;主进程持有真实 accelerator,面板显示 `taken`/`invalid` 注册失败原因 |
| `apps/desktop/src/app/settings/keys-settings.tsx` | 108 | Tools & Keys 页:按后端 `category` 分 `tools`/`settings` 两个子视图,`channel_managed` 的平台凭据在此隐藏 |
| `apps/desktop/src/app/settings/credential-key-ui.tsx` | 406 | 凭据 UI 组件族:`KeyField`(已设 → 只读遮罩输入,聚焦转编辑)、`CredentialKeyCard`、`ProviderKeyRows`、`isKeyVar`、`credentialPlaceholder`、`credentialRowLabel` |
| `apps/desktop/src/app/settings/ssh-host-selection.ts` | 43 | 两个纯 reducer:`selectSshHost`(换主机即清空派生字段)、`enrichSelectedSshHost`(用 ssh_config 解析结果只填空位) |

*(上表 24 行覆盖 21 个"面板"文件 + `credential-key-ui.tsx`、`keys-settings.tsx`、`ssh-host-selection.ts` 三个附属件;合计与清单一致。)*

### 0.5 `apps/desktop/src/app/settings/memory/` —— 记忆 provider 配置(4 文件 / 613 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/app/settings/memory/provider-config-panel.tsx` | 163 | 内联紧凑面板:只渲染 `inline` 字段,逐字段提交(单键 PUT),secret 保存后清空输入并把 `is_set` 打成 true |
| `apps/desktop/src/app/settings/memory/provider-config-modal.tsx` | 159 | "Full config…" 模态:按 `group` 分组渲染全部字段,只提交**改动过**的键(未动的键让运行时默认继续生效) |
| `apps/desktop/src/app/settings/memory/field-control.tsx` | 129 | 六种字段控件(bool/number/json/select/secret/text)与 `FieldTitle`;`onCommit` 存在与否决定"离散控件即时提交、文本控件失焦提交"还是"全是草稿" |
| `apps/desktop/src/app/settings/memory/connect.tsx` | 162 | provider OAuth 连接小挂件:能力由后端 404 与否决定,连接后 1.5s 轮询、120s 超时 |

### 0.6 `apps/desktop/src/app/settings/billing/` —— 计费(19 文件 / 3,752 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `apps/desktop/src/app/settings/billing/index.tsx` | 584 | Billing 页装配:`bview=overview|plans`、三张摘要卡、通知卡、Plan / Payment&credits / Usage 三节、`BuyCreditsRow` 实控件、DEV fixture 切换器 |
| `apps/desktop/src/app/settings/billing/use-billing-state.ts` | 840 | **视图模型层**:两个 react-query(`staleTime:0` + 30s 轮询)+ `deriveBillingView` 把两份 wire 响应折成 `BillingView`(notice / plan / paymentRow / refillRow / topupRow / tiers / usageRows / summary) |
| `apps/desktop/src/app/settings/billing/dev-fixtures.ts` | 469 | 16 个 DEV 预设账户状态(healthy / low / boundary / empty-overdrawn / cap-near / cap-hit / no-card / no-subscription / logged-out / refusal / billing-off / free-personal / subscriber-personal / pending-downgrade / pending-cancellation / auto-refill-divergent) |
| `apps/desktop/src/app/settings/billing/use-charge-poller.ts` | 297 | 一次充值的完整流程:`billing.charge` → `driveChargeSettlement` 轮询 → 结果映射为 success/failure/ambiguous;含幂等键复用判据与终态原因文案 |
| `apps/desktop/src/app/settings/billing/auto-reload-row.tsx` | 293 | 自动补款行的就地编辑(阈值/补到多少),零位移布局(编辑层常驻但 `invisible`),关闭时仍必须回传当前金额 |
| `apps/desktop/src/app/settings/billing/plans-view.tsx` | 229 | `bview=plans` 的套餐网格 + 降级的 preview→confirm 面板(焦点管理 + aria-live) |
| `apps/desktop/src/app/settings/billing/api.ts` | 193 | `BillingApi` 接口(9 个方法)+ 网关实现 + 拒绝信封归一化(`normalizeRefusal`/`normalizeThrown`)+ `BillingApiProvider`(DEV 用模拟实现整体替换) |
| `apps/desktop/src/app/settings/billing/use-subscription-change.ts` | 177 | 降级流程状态机(判别联合 5 态)+ 撤销流程(`subscription.resume`);同 tick 双击用 ref 互斥 |
| `apps/desktop/src/app/settings/billing/errors.ts` | 163 | `resolveRefusal`:拒绝码 → `{title, message, action}` 的**桌面文案表**(18 个 case + default) |
| `apps/desktop/src/app/settings/billing/use-step-up.ts` | 143 | 提权(Remote Spending 授权)流程:先订阅 `billing.step_up.verification` 事件拿设备码,再发 `billing.step_up` RPC |
| `apps/desktop/src/app/settings/billing/billing-amounts.ts` | 123 | 金额解析/夹取/校验/格式化(`clampAmount`/`parseAmount`/`formatAmountForRequest`/`validateAutoReloadInputs`/`validateBillingAmount`/`formatMoney`) |
| `apps/desktop/src/app/settings/billing/simulated-api.ts` | 89 | DEV fixture 的内存版 `BillingApi`:调度/撤销真的会改写这份可变副本,所以 fixture 点得动 |
| `apps/desktop/src/app/settings/billing/inline-feedback.tsx` | 70 | 两个内联反馈组件:`StepUpInlineAction`(验证码 + 打开验证页 + 消息 + 关闭)、`BillingRefusalInline` |
| `apps/desktop/src/app/settings/billing/tier-art.tsx` | 69 | 套餐缩略图:按**套餐名小写**(不是 tier_id,后者是随环境变的 cuid)查 4 张 webp + 混合模式;未知名返回 null |
| `apps/desktop/src/app/settings/billing/current-plan-card.tsx` | 57 | 当前套餐卡:名称/价格/说明 + 「查看套餐」按钮 **或** 门户外链(二选一)+ 待生效变更的 Undo |
| `apps/desktop/src/app/settings/billing/account-row-value.tsx` | 48 | 账户行右侧的通用渲染:value / pill / secondaryPill / chips / action |
| `apps/desktop/src/app/settings/billing/types.ts` | 35 | 纯转出层:把 `@hermes/shared/billing` 的 15 个类型原样再导出给 billing 目录内部用 |
| `apps/desktop/src/app/settings/billing/fixtures.test-util.ts` | 35 | 测试用 fixture 助手:`okBilling`/`okSubscription` 与两个 `endpoint_unavailable` 拒绝样本 |
| `apps/desktop/src/app/settings/billing/open-external.ts` | 9 | 一个可选参数版的外链打开器(视图模型里的 url 可能是 undefined) |

### 0.7 `apps/shared/` —— 桌面端与 TUI 共用的运行时无关包(12 文件 / 1,411 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `apps/shared/src/json-rpc-gateway.ts` | 429 | `JsonRpcGatewayClient`:WS 上的 JSON-RPC 客户端(URL 类型校验、15s 连接超时、120s 请求超时、AbortSignal、事件分发、关闭时拒绝全部 pending) |
| `apps/shared/src/billing-types.ts` | 363 | 计费的**线协议契约**:`BillingBlock`、`UsageModelData`、`KnownBillingRefusalCode`(24)、`BillingPaymentMethod`(判别联合)、`BillingStateResponse`、`SubscriptionStateResponse`、preview/upgrade 响应等 |
| `apps/shared/src/websocket-url.ts` | 151 | 网关 WS URL 解析:`resolveGatewayWsUrl`(OAuth 每次重铸票据、token 才允许回落缓存 URL)、`GatewayReauthRequiredError`、`buildHermesWebSocketUrl` |
| `apps/shared/src/skin.ts` | 110 | skin 的跨界面契约:43 个颜色 token + 6 个 branding token + `HermesSkin` 形状 |
| `apps/shared/src/charge-settlement.ts` | 89 | `driveChargeSettlement`:充值结算轮询状态机(2s 间隔、5min 上限、retry_after 上限 30s、6 种 outcome) |
| `apps/shared/src/skill-scaffold.ts` | 69 | `skillInvocationText`:把模型侧的 skill 脚手架正文还原为用户敲的 `/work …`,给老网关兜底 |
| `apps/shared/src/index.ts` | 68 | 包主入口:32 个转出(policy 5 + billing types 22 + settlement 5 + gateway 8 + skill 1 + skin 7 + ws 9,含类型) |
| `apps/shared/src/billing-policy.ts` | 46 | `BILLING_REFUSAL_POLICY`:24 个拒绝码 → `{recovery, ambiguousMidPoll?, reuseIdempotencyKey?}`,类型上对 `KnownBillingRefusalCode` **编译期穷尽** |
| `apps/shared/src/billing-payment-method.test-d.ts` | 24 | 编译期守卫:证明 `BillingPaymentMethod` 的 `kind` 仍可窄化(历史上写成 `string & {}` 会静默破坏窄化) |
| `apps/shared/package.json` | 24 | 私有工作区包 `@hermes/shared`,声明 5 个子路径导出(`.` / `./billing` / `./billing-policy` / `./charge-settlement` / `./skin`) |
| `apps/shared/tsconfig.json` | 15 | ES2023 / Bundler 解析 / strict / noEmit,`include: ["src"]` |
| `apps/shared/eslint.config.mjs` | 5 | 直接摊开仓库根的 `eslint.config.shared.mjs`,零本地规则 |

---

## 1. 这一簇解决什么问题

一句话:**把"用户能改的一切"收进一个覆盖层,并让每个开关落到正确的存储层与正确的 profile 上。**

难点不在于画表单,而在于这一簇同时面对**三种互不相同的存储权威**,外加**四种连接模式**和**多 profile 作用域**:

| 存储层 | 权威方 | 读写通道 | 本片代表 |
|---|---|---|---|
| `config.yaml` | 后端(CLI / 网关 / 桌面共享) | REST `GET/PUT /api/config` | `SECTIONS` 的 96 键 + `terminal.font_family` + `sessions.auto_archive*` |
| `.env` | 后端(profile 级) | REST `/api/env`(GET/PUT/DELETE) + `/api/env/reveal` | 凭据卡、toolset env 字段 |
| 设备本地 | 渲染进程 localStorage **或** Electron 主进程 | nanostores / IPC 桥 | 主题、缩放、通知、Quick Entry、卸载、连接配置 |

再叠一层:**计费**不是配置,是**会动钱的远程事务**——它有自己的拒绝码分类、幂等键、结算轮询与提权流程,并且这套契约必须与 TUI 逐字一致(所以住在 `apps/shared/`)。

---

## 2. 接缝穷举(判据 2)

> 本节每张表都给出**机械枚举命令**与条数。命令均以仓库根 `/home/user/hermes-agent` 为工作目录,任何人 clone 后可重跑。

### 2.1 设置导航面:17 个视图 + 5 个子视图 + 7 个 URL 参数

`apps/desktop/src/app/settings/index.tsx:47 @ 863e313`

```
const SETTINGS_VIEWS: readonly SettingsViewId[] = [
  ...SECTIONS.map(s => `config:${s.id}` as SettingsViewId),
  'providers',
  'gateway',
  'keybinds',
  'keys',
  'notifications',
  'billing',
  'plugins',
  'sessions',
  'about'
]
```

即 **8 个 `config:*`(来自 `SECTIONS`)+ 9 个专用视图 = 17**。

```verify
cd /home/user/hermes-agent
# 8 个 config 段
grep -c "^    id: '" apps/desktop/src/app/settings/constants.ts
# 9 个专用视图(SETTINGS_VIEWS 里的字面量)
sed -n '47,58p' apps/desktop/src/app/settings/index.tsx | grep -c "^  '"
```

**子视图与 URL 参数全表**(探针 `probe_c_seams.py` 第 5 节,9 条;其中 `aux` 属 model-settings 的辅助槽深链):

| 参数 | 取值域 | 定义处(锚点 + 摘录) | 作用 |
|---|---|---|---|
| `tab` | 17 个 `SettingsViewId` | `apps/desktop/src/app/settings/index.tsx:79` 的 `useRouteEnumParam` | 主视图 |
| `pview` | `accounts` / `keys` / `custom-endpoints` | `apps/desktop/src/app/settings/providers-settings.tsx:48`:`export const PROVIDER_VIEWS = ['accounts', 'keys', 'custom-endpoints'] as const` | Providers 子视图 |
| `kview` | `tools` / `settings` | `apps/desktop/src/app/settings/keys-settings.tsx:13`:`export const KEYS_VIEWS = ['tools', 'settings'] as const` | Keys 子视图 |
| `bview` | `overview` / `plans` | `apps/desktop/src/app/settings/billing/index.tsx:47`:`const BILLING_VIEWS = ['overview', 'plans'] as const` | Billing 子视图 |
| `field` | 任意 config 键 | `apps/desktop/src/app/settings/config-settings.tsx:204` 的 `targetField` | 命令面板深链到某一行配置 |
| `key` | 任意 env 键 | `apps/desktop/src/app/settings/keys-settings.tsx:46`:`param: 'key',` | 从 Capabilities 深链到某张凭据卡 |
| `session` | 会话 id | `apps/desktop/src/app/settings/sessions-settings.tsx:99`:`param: 'session',` | 深链到某条归档会话 |
| `server` | MCP server 名 | `apps/desktop/src/app/settings/index.tsx:73`:`const server = params.get('server')` | 仅用于把 `?tab=mcp` 老书签转发到 Capabilities |
| `aux` | 辅助任务键 | `apps/desktop/src/app/settings/model-settings.tsx:215` 的 `useDeepLinkHighlight` | 深链到某个辅助模型槽 |

**渲染派发的一个不对称**(容易看漏):`config:appearance` 在 `startsWith('config:')` **之前**被单独拦截,所以 `ConfigSettings` 永远不会渲染 appearance 段(该段 `keys: []`,本来也是空的)。

`apps/desktop/src/app/settings/index.tsx:302 @ 863e313`

```
          {activeView === 'config:appearance' ? (
            <AppearanceSettings />
          ) : activeView === 'about' ? (
```

### 2.2 config.yaml 键全表:96(SECTIONS)+ 5(段外)= 101,与 R8A 全仓 856 键表对账

`apps/desktop/src/app/settings/constants.ts:638 @ 863e313`

```
export const SECTIONS: DesktopConfigSection[] = [
  {
    id: 'model',
    label: 'Model',
    icon: Box,
    keys: ['model_context_length', 'fallback_providers']
```

```verify
cd /home/user/hermes-study
python3 data/r10b/probes/probe_c_config_keys.py /home/user/hermes-agent
```

实测输出(逐段条数,合计 96,去重后仍 96):

```text
  section model      label=Model            keys=2
  section chat       label=Chat             keys=4
  section appearance label=Appearance       keys=0
  section workspace  label=Workspace        keys=8
  section safety     label=Safety           keys=9
  section memory     label=Memory & Context keys=10
  section voice      label=Voice            keys=41
  section advanced   label=Advanced         keys=22
  TOTAL sections=8 keys=96 unique=96
```

**SECTIONS 之外、本片仍会读写的 config 键(5 个,逐条列全)**:

| 键 | 读/写处(锚点 + 摘录) | 是否在 R8A 856 键表 |
|---|---|---|
| `terminal.font_family` | `apps/desktop/src/app/settings/terminal-font-setting.tsx:25` 的 `normalizeTerminalFontFamily` | 是 |
| `sessions.auto_archive` | `apps/desktop/src/app/settings/sessions-settings.tsx:223`:`auto_archive: autoArchive,` | 是 |
| `sessions.auto_archive_days` | `apps/desktop/src/app/settings/sessions-settings.tsx:224`:`auto_archive_days: archiveDays` | 是 |
| `agent.personalities` | `apps/desktop/src/app/settings/helpers.ts:161`:`const custom = getNested(config, 'agent.personalities')` | **否** |
| `agent.reasoning_effort` | `apps/desktop/src/app/settings/model-settings.tsx:508` 的 `rawEffort` | **否** |

加上 `SECTIONS` 里同样不在 R8A 表中的 `model_context_length`,**桌面设置面触及的 101 个键里有 3 个落在 R8A 资产之外**。三者都不是幻觉键,而是 R8A 表的**采集口径**决定的盲区(见 §5 ◇-2)。

`sectionFieldEntries` 决定"某键是否真的渲染成一行":后端 schema 没声明**且**配置里没有该值时,整行不渲染。所以 `model_context_length` 之类的合成键只有在后端 schema 声明了才出现。

`apps/desktop/src/app/settings/helpers.ts:117 @ 863e313`

```
export function sectionFieldEntries(
  schema: Record<string, ConfigFieldSchema>,
  config: HermesConfigRecord
): Map<string, [string, ConfigFieldSchema][]> {
  return new Map(
    SECTIONS.map(s => [
      s.id,
      s.keys.flatMap(k => {
        const value = getNested(config, k)
        const field = schema[k] ?? (value === undefined ? undefined : inferFieldSchema(value))

        return field ? [[k, field] as [string, ConfigFieldSchema]] : []
      })
    ])
  )
}
```

Voice 段的 41 键里,只有当前选中 provider 的子键会显示:

`apps/desktop/src/app/settings/config-settings.tsx:42 @ 863e313`

```
export function voiceFieldVisible(key: string, config: HermesConfigRecord): boolean {
  const match = /^(tts|stt)\.([^.]+)\./.exec(key)

  if (!match) {
    return true
  }

  const [, domain, provider] = match

  if (domain === 'stt' && !getNested(config, 'stt.enabled')) {
    return false
  }

  return provider === String(getNested(config, `${domain}.provider`) ?? '')
}
```

### 2.3 env 凭据面:4 条 REST + 3 个 category 分流

`apps/desktop/src/hermes.ts` 里本片用到的 4 条 env 路由(全列,无抽样):

| 助手 | 方法 + 路径 | 锚点(锚点 + 摘录) |
|---|---|---|
| `getEnvVars` | `GET /api/env` | `apps/desktop/src/hermes.ts:774`:`export function getEnvVars(): Promise<Record<string, EnvVarInfo>> {` |
| `setEnvVar` | `PUT /api/env` | `apps/desktop/src/hermes.ts:781`:`export function setEnvVar(key: string, value: string): Promise<{ ok: boolean }> {` |
| `deleteEnvVar` | `DELETE /api/env` | `apps/desktop/src/hermes.ts:839`:`export function deleteEnvVar(key: string): Promise<{ ok: boolean }> {` |
| `revealEnvVar` | `POST /api/env/reveal` | `apps/desktop/src/hermes.ts:848`:`export function revealEnvVar(key: string): Promise<{ key: string; value: string }> {` |

四条都经 `profileScoped()`,即凭据天然是 **per-profile** 的。

后端 `category` → 桌面页面的**完整分流**(三条,穷尽):

`apps/desktop/src/app/settings/keys-settings.tsx:26 @ 863e313`

```
const VIEW_CATEGORIES: Record<KeysView, readonly string[]> = {
  settings: ['setting', 'messaging'],
  tools: ['tool']
}
```

Providers 页的那一档是显式过滤掉的:

`apps/desktop/src/app/settings/providers-settings.tsx:67 @ 863e313`

```
  for (const [key, info] of Object.entries(vars)) {
    if (info.category !== 'provider') {
      continue
    }
```

- `category === 'provider'` → Providers 页
- `category ∈ {'setting','messaging'}` 且 `!channel_managed` → Keys 页 `settings` 子视图
- `category === 'tool'` → Keys 页 `tools` 子视图
- `channel_managed === true` 的 `messaging` 行 → 本片**不显示**,归 Messaging 页

### 2.4 Electron 主进程桥:36 个成员

```verify
cd /home/user/hermes-study
python3 data/r10b/probes/probe_c_bridge_and_shared.py /home/user/hermes-agent
```

实测 **36 个 `window.hermesDesktop.*` 成员**被本片调用(探针同时识别 `const desktop = window.hermesDesktop` 别名形式)。按职能归类,逐个列全:

| 类别 | 成员 |
|---|---|
| 连接配置(7) | `getConnectionConfig`、`saveConnectionConfig`、`applyConnectionConfig`、`testConnectionConfig`、`probeConnectionConfig`、`oauthLoginConnectionConfig`、`oauthLogoutConnectionConfig` |
| Hermes Cloud(5) | `cloud`、`cloud.login`、`cloud.logout`、`cloud.discover`、`cloud.agentSignIn` |
| SSH(2) | `sshConfigHosts`、`sshResolveHost` |
| 网关生命周期(7) | `getConnection`、`revalidateConnection`、`onBootProgress`、`onBackendExit`、`onConnectionApplied`、`onPowerResume`、`onWindowStateChanged` |
| profile(1) | `profile.get` |
| 会话/目录设置(5) | `settings`、`getDefaultProjectDir`、`setDefaultProjectDir`、`pickDefaultProjectDir`、`sessions` |
| 系统动作(6) | `openExternal`、`openDir`、`revealPath`、`revealLogs`、`desktopPluginsRoot`、`terminal` |
| 卸载(2) | `uninstall`、`run` |
| 主题(1) | `themes.searchMarketplace` |

*(`cloud`/`settings`/`sessions`/`uninstall` 既作为命名空间对象出现,也各自有二级成员;探针把两者都计入,故 36 含 4 个命名空间根。)*

### 2.5 网关 JSON-RPC:后端声明 10,桌面调 9

```verify
cd /home/user/hermes-study
python3 data/r10b/probes/probe_c_billing_codes.py /home/user/hermes-agent
```

```text
declared in tui_gateway/methods_session.py: 10 -> ['billing.state', 'subscription.state', 'subscription.preview', 'subscription.change', 'subscription.resume', 'subscription.upgrade', 'billing.charge', 'billing.charge_status', 'billing.auto_reload', 'billing.step_up']
called by desktop BillingApi              : 9 -> ['billing.auto_reload', 'billing.charge', 'billing.charge_status', 'billing.state', 'billing.step_up', 'subscription.change', 'subscription.preview', 'subscription.resume', 'subscription.state']
declared but NOT called by desktop        : ['subscription.upgrade']
```

外加 **1 个网关→客户端事件**:`billing.step_up.verification`

`apps/desktop/src/app/settings/billing/use-step-up.ts:85 @ 863e313`

```
      gateway?.on<StepUpVerificationPayload>('billing.step_up.verification', event => {
```

### 2.6 计费拒绝码:24 个线上码,三张表的对齐情况

三张表必须对齐,实际只有前两张对齐:

1. `KnownBillingRefusalCode`(`apps/shared/src/billing-types.ts:67`)—— **24** 个
2. `BILLING_REFUSAL_POLICY`(`apps/shared/src/billing-policy.ts:11`)—— **24** 个,且类型为 `Record<KnownBillingRefusalCode, …>`,**编译期穷尽**
3. `resolveRefusal` 的 switch(`apps/desktop/src/app/settings/billing/errors.ts:23`)—— **18** 个 case(含 2 个非线上码 `timeout`/`transport`),即只覆盖 24 个线上码中的 **16** 个

探针逐码输出(24 行全列,不抽样):

```text
code                            policy.recovery   desktop copy?
  auto_top_up_disabled_failures portal            NO -> generic default
  cli_billing_disabled          portal            yes
  consent_required              portal            yes
  endpoint_unavailable          retry             yes
  idempotency_conflict          none              yes
  idempotency_key_required      none              NO -> generic default
  insufficient_scope            step_up           yes
  internal_error                retry             NO -> generic default
  invalid_charge_id             none              NO -> generic default
  invalid_request               none              NO -> generic default
  monthly_cap_exceeded          portal            yes
  network_error                 retry             NO -> generic default
  no_payment_method             portal            yes
  org_access_denied             portal            yes
  preview_rejected              none              NO -> generic default
  rate_limited                  retry             yes
  remote_spending_disabled      portal            yes
  remote_spending_revoked       reconnect         yes
  role_required                 portal            yes
  session_revoked               login             yes
  stripe_unavailable            retry             yes
  temporarily_unavailable       retry             yes
  upgrade_cap_exceeded          none              yes
  validation_failed             none              NO -> generic default
```

### 2.7 `@hermes/shared` 的导出面与消费面

包声明 **5 个子路径导出**;探针实测 **5 个全部有真实消费者**,且跨 desktop 与 ui-tui 两个界面:

| 子路径 | 消费文件数 | 消费方 |
|---|---|---|
| `@hermes/shared` | 15 | 全在 `apps/desktop/src/`(gateway hooks、store、hermes.ts、global.d.ts、lib、session hooks) |
| `@hermes/shared/billing` | 5 | `apps/desktop/src/app/settings/billing/types.ts`、`.../errors.test.ts`、`ui-tui/src/gatewayTypes.ts`、`ui-tui/src/lib/billingDialog.ts(.test)` |
| `@hermes/shared/billing-policy` | 1 | `apps/desktop/src/app/settings/billing/use-charge-poller.ts` |
| `@hermes/shared/charge-settlement` | 2 | 同上 + `ui-tui/src/app/slash/commands/topup.ts` |
| `@hermes/shared/skin` | 6 | `apps/desktop/src/themes/*`(3)、`apps/desktop/src/app/session/hooks/.../gateway-event.ts`、`ui-tui/src/gatewayTypes.ts`、`ui-tui/src/theme.ts` |

`apps/shared/src/index.ts` 的主入口共 **32 项转出**(policy 5 / billing types 22 / settlement 5 / json-rpc 8 / skill 1 / skin 7 / websocket 9 —— 含 `type` 转出,合计按 export 语句内的标识符计)。

### 2.8 设备本地存储面:25 个 store 模块

```verify
cd /home/user/hermes-agent
python3 - <<'EOF'
import re, pathlib
repo = pathlib.Path('.')
files = [l.strip() for l in pathlib.Path('/home/user/hermes-study/data/r10b/slices/C.txt').read_text().splitlines() if l.strip()]
IMPORT = re.compile(r"import\s+(?:type\s+)?\{([^}]*)\}\s+from\s+'(@/store/[^']+)'", re.S)
mods = {}
for rel in files:
    p = repo/rel
    if not p.exists() or p.suffix not in {'.ts','.tsx'}: continue
    for m in IMPORT.finditer(p.read_text()):
        mods.setdefault(m.group(2), set()).update(n.strip() for n in m.group(1).split(',') if n.strip())
print(len(mods))
EOF
```

实测 **25 个 `@/store/*` 模块**。其中**承载"用户偏好"、由设置面板直接写入**的 14 个,按持久化层归类(逐个列全):

| 持久化层 | store | 写入面板 |
|---|---|---|
| localStorage(`@/lib/storage`) | `@/store/backdrop`、`@/store/translucency`、`@/store/reactions-enabled`、`@/store/completion-sound`、`@/store/native-notifications`、`@/store/keep-awake`(另镜像给主进程) | Appearance / Notifications / Advanced |
| localStorage(`persistentAtom`) | `@/store/embed-consent` | Appearance |
| localStorage(裸) | `@/store/tool-view` | Appearance |
| Electron 主进程 | `@/store/zoom`(`hermesDesktop.zoom.*`)、`@/store/quick-entry`(`hermesDesktop.quickEntry.*`)、`@/store/data-url-read-max` | Appearance / Advanced / Chat |
| 网关 RPC | `@/store/pet`、`@/store/pet-gallery` | Appearance→Pet |
| 键位存储 | `@/store/keybinds` | Keybinds |

**这就是本片最容易被忽略的接缝:同一个"设置"页面里,相邻两行可能写向三种完全不同的权威。** 代码里的注释把这件事说破了——两个设备本地开关(keep-awake、Quick Entry)被**有意**放进 Advanced 段,和 config.yaml 字段混排:

`apps/desktop/src/app/settings/config-settings.tsx:305 @ 863e313`

```
      {/* Device-local desktop prefs (not config.yaml) — they live here since
          keeping the machine awake and the global Quick Entry chord are both
          power-user, this-computer-only knobs. */}
      {activeSectionId === 'advanced' && (
        <>
          <ToggleRow
            checked={keepAwake}
            description={c.keepAwakeDesc}
            label={c.keepAwakeTitle}
            onChange={setKeepAwake}
          />
          <QuickEntrySettings />
        </>
      )}
```


---

## 3. 端到端链(判据 3)

### 3.1 链 A:改一个 config 值 → 落盘 config.yaml(6 跳)

**用户动作**:Settings → Voice,把 TTS Provider 从 `edge` 改成 `openai`。

1. **组件** —— `ConfigField` 判定这是个枚举字段,渲染 Select。
   `apps/desktop/src/app/settings/config-field.tsx:133 @ 863e313`
   ```
   if (selectOptions) {
     return row(
       <Select
         onValueChange={next => onChange(next === EMPTY_SELECT_VALUE ? '' : next)}
   ```

2. **回调** —— 段容器把 `onChange` 接到 `setNested` + `updateConfig`。
   `apps/desktop/src/app/settings/config-settings.tsx:340 @ 863e313`
   ```
                 onChange={value => updateConfig(setNested(config, key, value))}
   ```

3. **状态** —— `updateConfig` 只做三件事:版本号 +1、写草稿、触发防抖 effect。
   `apps/desktop/src/app/settings/config-settings.tsx:185 @ 863e313`
   ```
     const updateConfig = (next: HermesConfigRecord) => {
       saveVersionRef.current += 1
       setConfig(next)
       setSaveVersion(saveVersionRef.current)
     }
   ```

4. **纯函数** —— `setNested` 深拷贝 + 逐段防原型污染,返回新记录(不改原对象)。
   `apps/desktop/src/app/settings/helpers.ts:134 @ 863e313`
   ```
   export function setNested(obj: HermesConfigRecord, path: string, value: unknown): HermesConfigRecord {
     const clone = structuredClone(obj)
     const parts = configPathParts(path)
     let cur: Record<string, unknown> = clone
   ```

5. **协议** —— 550ms 后整份记录 `PUT /api/config`,成功后回写共享缓存。
   `apps/desktop/src/hermes.ts:748 @ 863e313`
   ```
   export function saveHermesConfig(config: HermesConfigRecord): Promise<{ ok: boolean }> {
     return window.hermesDesktop.api<{ ok: boolean }>({
       ...profileScoped(),
       path: '/api/config',
       method: 'PUT',
       body: { config }
     })
   }
   ```

6. **内核** —— 服务端**不做全量替换**,而是先反规范化再深合并到磁盘配置上,否则 schema 之外的根键(`custom_providers`、`agent.personalities`…)会被静默抹掉。
   `hermes_cli/web_server.py:6921 @ 863e313`
   ```
               existing = read_raw_config()
               incoming = _denormalize_config_from_web(body.config)
               save_config(_deep_merge(existing, incoming))
   ```

**这条链上的一个"隐形键"**:`model` 在 config.yaml 里可以是字符串也可以是 dict;GET 时被拍扁成字符串,并额外**合成**一个顶层 `model_context_length` 给前端编辑,PUT 时再折回 `model.context_length`。这就是为什么 `SECTIONS` 里有一个 R8A 表查不到的键。

`hermes_cli/web_server.py:4861 @ 863e313`

```
    config = dict(config)  # shallow copy
    model_val = config.get("model")
    if isinstance(model_val, dict):
        # Extract context_length before flattening the dict
        ctx_len = model_val.get("context_length", 0)
        config["model"] = model_val.get("default", model_val.get("name", ""))
        config["model_context_length"] = ctx_len if isinstance(ctx_len, int) else 0
    else:
        config["model_context_length"] = 0
    return config
```

### 3.2 链 B:点 "Buy" → 网关下单 → 结算轮询(7 跳)

**用户动作**:Settings → Billing → Payment & credits → 选 $100 → Buy。

1. **组件** —— Buy 按钮;`canBuy` 要求非忙、有卡、金额夹取后非空。
   `apps/desktop/src/app/settings/billing/index.tsx:213 @ 863e313`
   ```
           <Button disabled={!canBuy} onClick={startBuy} size="xs" type="button" variant="secondary">
             Buy
           </Button>
   ```

2. **状态机** —— `useChargeFlow.start`:只有**上一次拒绝被判为可复用幂等键**时才带上旧 key。
   `apps/desktop/src/app/settings/billing/use-charge-poller.ts:200 @ 863e313`
   ```
         const retryIntent = retryIntentRef.current
         const idempotencyKey = retryIntent?.amountUsd === amountUsd ? retryIntent.idempotencyKey : undefined

         setOutcome(null)
         setPhaseState('charging')

         const chargeResult = await api.charge(amountUsd, idempotencyKey)
   ```

3. **API 层** —— 没带 key 就现场 `crypto.randomUUID()` 铸一个。
   `apps/desktop/src/app/settings/billing/api.ts:146 @ 863e313`
   ```
   export const createBillingApi = (requestGateway: BillingRequestGateway): BillingApi => ({
     charge: async (amountUsd, idempotencyKey = crypto.randomUUID()) => {
       const result = await callBilling<BillingChargeResponse>(requestGateway, 'billing.charge', {
         amount_usd: amountUsd,
         idempotency_key: idempotencyKey
       })

       return { ...result, idempotencyKey }
     },
   ```

4. **传输封装** —— `useGatewayRequest().requestGateway`,带断线自愈。
   `apps/desktop/src/app/gateway/hooks/use-gateway-request.ts:115 @ 863e313`
   ```
           return await gateway.request<T>(method, params, timeoutMs, signal)
   ```

5. **协议** —— 共享包里的 JSON-RPC 客户端把它写进 socket。
   `apps/shared/src/json-rpc-gateway.ts:337 @ 863e313`
   ```
         try {
           socket.send(
             JSON.stringify({
               jsonrpc: '2.0',
               id,
               method,
               params
             })
           )
   ```

6. **内核** —— 网关侧 `billing.charge` 处理器;注意它**也会**在缺 key 时自己铸一个,并把 key 回显在错误信封里"给 TUI 重试复用"。
   `tui_gateway/methods_session.py:2177 @ 863e313`
   ```
       key = params.get("idempotency_key") or new_idempotency_key()
       try:
           result = post_charge(amount_usd=amount, idempotency_key=key)
           return _ok(rid, {"ok": True, "charge_id": result.get("chargeId"), "idempotency_key": key})
   ```

7. **结算轮询** —— 拿到 `charge_id` 后交给共享包的状态机(2s 间隔 / 5min 上限 / `retry_after` 封顶 30s / 6 种 outcome)。
   `apps/shared/src/charge-settlement.ts:28 @ 863e313`
   ```
   export async function driveChargeSettlement(deps: SettlementDeps): Promise<SettlementOutcome> {
     const start = deps.now()
     const timedOut = (): boolean => deps.now() - start >= SETTLEMENT_POLL_CAP_MS
   ```

**链 B 上的缺陷见 §6 ■-1**:第 2 跳判定"是否复用幂等键"用的是桌面自己硬编的集合,而不是共享 policy 上的 `reuseIdempotencyKey` 标记,两者对 2 个码不一致。

---

## 4. 逐区域要点

### 4.1 网关连接:四种模式 + 每 profile 覆盖

`apps/desktop/src/app/settings/gateway-settings.tsx:34` 定义 `type Mode = 'local' | 'remote' | 'cloud' | 'ssh'`,四张 `ModeCard` 全部无条件渲染(`:1070`–`:1103`)。

- **scope**:`scope === null` 是全局连接,否则是某个具名 profile 的**每 profile 覆盖**;`default` profile 用全局连接,所以 chip 列表 = `profiles.filter(p => p.name !== 'default')`。切 scope 会清空本地输入的 token,防止跨 scope 泄漏(`:229`–`:232`)。
- **envOverride**:环境变量强制指定连接时整页禁用并挂红条(`:1055`)。
- **认证方式判定**:输入远端 URL → 500ms 防抖 → `probeConnectionConfig` 打公开的 `/api/status` → 得知这台网关是 OAuth 还是静态 token。**在探测落地前两个控件都不渲染**,否则默认值 `token` 会让每台 OAuth 网关都先闪一下 token 输入框。

  `apps/desktop/src/app/settings/gateway-settings.tsx:338 @ 863e313`

  ```
    const authResolved = useMemo(() => {
      if (probeStatus === 'done') {
        return true
      }

      return probeStatus === 'idle' && hasSavedRemote
    }, [probeStatus, hasSavedRemote])
  ```

- **password provider**:只有**全部**广告出来的 provider 都 `supportsPassword` 才切成密码版文案,混合部署保持通用 OAuth 措辞。

  `apps/desktop/src/app/settings/gateway-settings.tsx:367 @ 863e313`

  ```
    const isPasswordProvider = useMemo(() => {
      const providers: DesktopAuthProvider[] = probe?.providers ?? []

      return providers.length > 0 && providers.every(p => p.supportsPassword)
    }, [probe])
  ```

- **cloud**:一次门户登录 → `cloud.discover(org)`;多组织返回 `needsOrgSelection` 时先出组织选择器。选中 agent 后走 `cloud.agentSignIn`(静默级联,不再弹第二次授权),再以 cloud 模式 `applyConnectionConfig`。选中的 org 通过 **ref 而非 state** 读取(`cloudOrgRef`,`:194`),因为发现是异步的、用户可能在同一 render tick 里就点 Connect。
- **ssh**:主机可从 `~/.ssh/config` 建议列表选,也可切 Custom 自由输入;`selectSshHost`/`enrichSelectedSshHost` 两个纯 reducer 保证"换主机清空派生字段、解析结果只填空位"。7 类 `sshError` 有专属文案(`:497`–`:505` 与 `:932`–`:941` 两处**各写了一份**,后者多一个 `unknown` 键)。

**AGENTS.md 的两条自证不变量在本片成立**(这属于"文档说的代码做到了",一并记录):

`apps/desktop/AGENTS.md:127 @ 863e313`

> - **One-time credentials are never reused.** An OAuth gateway connection mints a
>   fresh WebSocket ticket on every dial and never falls back to the cached URL.

对照实现:OAuth 分支拿不到票据就抛错,**从不**回落 `conn.wsUrl`;只有非 OAuth 分支才允许"铸不到就用缓存 URL"这一低档位。

`apps/shared/src/websocket-url.ts:81 @ 863e313`

```
  if (mint) {
    const fresh = await mint(profile).catch(() => null)

    if (typeof fresh === 'string') {
      return fresh
    }

    if (fresh?.ok) {
      return fresh.wsUrl
    }
  }

  return conn.wsUrl
```

第二条("连接测试必须走真正要用的那条腿")也成立:主进程的 `testDesktopConnectionConfig` 在 HTTP `/api/status` 之后**还会真开一次 WS**。

`apps/desktop/electron/main.ts:7883 @ 863e313`

```
  if (wsUrl && typeof globalThis.WebSocket === 'function') {
    const probe = await probeGatewayWebSocket(wsUrl, { WebSocketImpl: globalThis.WebSocket })
```

### 4.2 凭据处理面(本项目历轮的重点)

**桌面有两条互不相同的凭据 UI 路径,遮罩策略不同:**

| 路径 | 明文回显? | 证据 |
|---|---|---|
| Settings → Providers / Keys(`credential-key-ui.tsx`) | **否**,只显示服务端给的 `redacted_value` | `apps/desktop/src/app/settings/credential-key-ui.tsx:68`:`const masked = info.redacted_value ?? '••••••••'` |
| Capabilities → toolset 面板(`toolset-config-panel.tsx`) | **是**,菜单里有 Reveal,渲染成明文块 | `apps/desktop/src/app/settings/toolset-config-panel.tsx:190`:`{revealed || '---'}` |

已设值的输入框是**只读 + 聚焦即转编辑**,输入类型按 `is_password` 切换:

`apps/desktop/src/app/settings/credential-key-ui.tsx:85 @ 863e313`

```
  if (info.is_set && !editing) {
    return (
      <Input
        className={cn(CREDENTIAL_CONTROL_CLASS, bare && CRED_BARE, 'cursor-pointer text-muted-foreground')}
        onFocus={startEdit}
        readOnly
        value={masked}
      />
    )
  }
```

保存成功后,页面**不重新拉取**,而是本地乐观地把 `redacted_value` 换成客户端自算的遮罩——这就是 §6 ■-2 的来源。

### 4.3 计费视图模型

`deriveBillingView` 把两份 wire 响应折成 4 种 `status`:`loading` / `refusal` / `logged_out` / `normal`。几个值得记的判断:

- **`can_change_plan` 与 `context`** 共同决定"能不能在应用内换套餐"。团队/组织账号一律不给应用内动作,只给门户外链。

  `apps/desktop/src/app/settings/billing/use-billing-state.ts:338 @ 863e313`

  ```
  function plansCapable(
    subscription: null | SubscriptionStateResponse,
    subscriptionResult: BillingResult<SubscriptionStateResponse> | undefined
  ): boolean {
    if (!subscription || (subscriptionResult && !subscriptionResult.ok)) {
      return false
    }

    return subscription.context !== 'team' && Boolean(subscription.can_change_plan)
  }
  ```

- **升级 vs 降级不对称**:升级 = 门户深链(`Choose ↗`),降级 = 应用内 preview→confirm→schedule。原因写在 `derivePlanTiers` 的 doc 注释里。
- **`payment_method` 与 `card` 的关系**在 `apps/shared/src/billing-types.ts:130`–`:141` 讲得很清楚:`card` 是有损的旧视图,只在支付方式是卡时才有值;**`!card` 不等于"没有支付方式"**。但视图模型的 `noCardNotice`/`paymentMethodRow`/`buyCreditsRow` **全部只看 `billing.card`**,没有一处读 `payment_method`。对一个 Link 客户,页面会顶着"No payment method on file"的告警条,并把 Buy 按钮禁用。

  ```verify
  cd /home/user/hermes-agent
  # 桌面 billing 目录里 payment_method 的全部出现处(只在类型转出里,无逻辑读取)
  grep -rn "payment_method" apps/desktop/src/app/settings/billing/
  ```

  实测只在 `types.ts` 的类型转出与 `use-billing-state.ts` 之外出现 0 次逻辑读取。**这条按"负结论必须写搜索面"的规矩标注**:搜索面 = `apps/desktop/src/app/settings/billing/` 全目录、模式 `payment_method`、无排除。这是**已知的类型注释与实现之间的落差**,但由于 `BillingPaymentMethod` 明说"老网关会整字段缺席",不能断定为缺陷(缺席时确实只能看 `card`);记为移交项 H-R10B-C-j。

- **DEV fixture 通道**:`BillingApiProvider` 用 context 整体替换 `BillingApi`,所以 16 个 fixture 走的是**和线上完全相同的 query 路径**,没有任何 fixture 短路分支。这是个值得抄的设计。

  `apps/desktop/src/app/settings/billing/api.ts:183 @ 863e313`

  ```
  const BillingApiContext = createContext<BillingApi | null>(null)

  export const BillingApiProvider = BillingApiContext.Provider

  export function useBillingApi(): BillingApi {
    const override = useContext(BillingApiContext)
    const { requestGateway } = useGatewayRequest()
    const real = useMemo(() => createBillingApi(requestGateway), [requestGateway])

    return override ?? real
  ```

- **套餐缩略图按名字查表,不按 id**:真实 `tier_id` 是随环境变的 Prisma cuid,名字才稳定。

  `apps/desktop/src/app/settings/billing/tier-art.tsx:28 @ 863e313`

  ```
  const TIER_ART: Record<string, TierArtSpec> = {
    free: { blend: 'screen', src: connectArt },
    plus: { blend: 'screen', src: memoryArt },
    starter: { blend: 'screen', src: connectArt },
    super: { blend: 'lighten', src: automationArt },
    ultra: { blend: 'normal', src: sandboxArt }
  }
  ```


### 4.4 `apps/shared` 的定位

包里没有一行 React、没有硬 DOM 依赖:

`apps/shared/src/websocket-url.ts:113 @ 863e313`

```
function readWindowLocation(): { host: string; protocol: string } {
  if (typeof window === 'undefined') {
    return { host: '', protocol: 'http:' }
  }

  return { host: window.location.host, protocol: window.location.protocol }
}
```

它承载的是**必须逐字一致的跨界面契约**:

- 线协议形状(`billing-types.ts`、`skin.ts`)
- 分类策略(`billing-policy.ts`)
- 时序状态机(`charge-settlement.ts`、`json-rpc-gateway.ts`)
- 与 Python 侧字节对齐的字符串标记(7 个常量,注释写明 "mirror `agent/skill_commands.py` byte for byte")

`apps/shared/src/skill-scaffold.ts:16 @ 863e313`

```
const INVOCATION_PREFIX = '[IMPORTANT: The user has invoked the '
const SINGLE_MARKER = 'The full skill content is loaded below.]'
const SINGLE_INSTRUCTION = 'The user has provided the following instruction alongside the skill invocation: '
const RUNTIME_NOTE = '\n\n[Runtime note:'
const BUNDLE_MARKER = ' skill bundle,'
const BUNDLE_INSTRUCTION = '\nUser instruction: '
const BUNDLE_SKILL_BLOCK = '\n\n[Loaded as part of the '
```


`apps/shared/src/billing-types.ts:59` 那段注释把"为什么要把码集合闭起来"讲透了:闭集 + `Record<KnownBillingRefusalCode, …>` = 新增一个码却忘了映射时**编译不过**。这个机制在 `billing-policy.ts` 上生效了,在桌面的 `errors.ts` 上没生效(见 §6 ■-5)。

---

## 5. 文档与代码的出入

### ▲-1 `cli.md` 教用户把 personalities 写在顶层,四处运行时都读 `agent.personalities`

`website/docs/user-guide/cli.md:228 @ 863e313`

> You can also define custom personalities in `~/.hermes/config.yaml`:

紧随其后的 YAML 例子(`website/docs/user-guide/cli.md:230`–`:236`)把键写在**顶层**:

`website/docs/user-guide/cli.md:231 @ 863e313`

> personalities:
>   helpful: "You are a helpful, friendly AI assistant."

而运行时**四个**读取点全部走 `agent.personalities`:

| 读取点(锚点 + 摘录) | 界面 |
|---|---|
| `cli.py:4490`:`self.personalities = CLI_CONFIG["agent"].get("personalities", {})` | classic CLI |
| `gateway/slash_commands.py:2502`:`personalities = cfg_get(config, "agent", "personalities", default={})` | 消息网关 |
| `tui_gateway/server.py:5815` 的 `_available_personalities` | TUI |
| `apps/desktop/src/app/settings/helpers.ts:161`:`const custom = getNested(config, 'agent.personalities')` | 桌面 |

桌面侧的读法是**对的**:

`apps/desktop/src/app/settings/helpers.ts:160 @ 863e313`

```
function personalityOptions(config: HermesConfigRecord): string[] {
  const custom = getNested(config, 'agent.personalities')

  const customNames =
    custom && typeof custom === 'object' && !Array.isArray(custom) ? Object.keys(custom as Record<string, unknown>) : []

  return [...new Set(['', ...BUILTIN_PERSONALITIES, ...customNames])]
}
```

**为什么这条会静默失败**:`DEFAULT_CONFIG` 里恰好**也**声明了一个顶层 `personalities: {}`(带注释 "Custom personalities — add your own entries here"),并且 `personalities` 在 `_OPEN_DICT_TOP_LEVEL_KEYS` 里,所以按 `cli.md` 写出来的 config **通过 schema 校验、不报错、然后永远没人读**。

`hermes_cli/config_defaults.py:2126 @ 863e313`

```
    # Custom personalities — add your own entries here
    # Supports string format: {"name": "system prompt"}
    # Or dict format: {"name": {"description": "...", "system_prompt": "...", "tone": "...", "style": "..."}}
    "personalities": {},
```

另一页文档写的是对的(`website/docs/user-guide/features/personality.md:214` 明说 "under `agent.personalities`"),所以这是**两页文档互相矛盾、其中一页与代码矛盾**。
*判定范围*:▲ 只落在 `website/docs/user-guide/cli.md:228`–`:236` 这一句加它的 YAML 块上(散文句"你也可以在 config.yaml 里定义自定义 personalities"本身为真,假的是块里的嵌套层级),归 `website/docs/user-guide/cli.md:214` 的 `## Personalities` 标题管。

### ▲-2 `DESIGN.md` 说"每个面向用户的字符串都走 `useI18n()`",整个 Billing 页不走

`apps/desktop/DESIGN.md:285 @ 863e313`

> - Every user-facing string goes through `useI18n()` (`src/i18n/context.tsx`).
>   No literals in JSX.

```verify
cd /home/user/hermes-study
python3 data/r10b/probes/probe_c_i18n.py /home/user/hermes-agent
```

实测:

```text
.tsx files in slice C            : 44
  without useI18n/translateNow   : 17
  ...and shipping literal copy   : 11   (total literal sites: 76)
```

**探针是保守的、会低报**:它只认 `title=`/`label=`/`description=`/`placeholder=`/`aria-label=` 等直写字面量与裸 JSX 文本,不认三元里的字面量,也**完全不看 `.ts` 文件**——而 Billing 的绝大部分文案恰恰住在两个 `.ts` 视图模型里:

- `apps/desktop/src/app/settings/billing/errors.ts` 的 18 个 `title`/`message` 全是硬编英文
- `apps/desktop/src/app/settings/billing/use-billing-state.ts` 的 notice / row title / caption 同理

举两个可点名的:

`apps/desktop/src/app/settings/billing/index.tsx:518 @ 863e313`

```
        <SettingsSection icon={Package} title="Plan">
```

`apps/desktop/src/app/settings/billing/use-billing-state.ts:320 @ 863e313`

```
  return {
    action: { label: 'Add card ↗', url: billing.portal_url ?? FALLBACK_PORTAL_BILLING_URL },
    message: 'Buying top-up credits and auto-refill stay disabled until a card is on file. Add one on the portal.',
    title: 'No payment method on file',
    tone: 'warn'
  }
```

Billing 是 `settings/index.tsx:167` 侧栏里的一个正式导航项、`:330` 会被渲染的正式页面,不是隐藏实验区。同类还有 `uninstall-section.tsx`(14 处)、`custom-endpoints-settings.tsx`(18 处)、`computer-use-panel.tsx`(10 处)。
*判定范围*:`apps/desktop/DESIGN.md:283` 的 `## i18n` 标题下,`:285`–`:286` 这一条是一个无限定的全称句("Every … No literals in JSX."),因此整条被证伪,记 ▲。

### ◎-1 `apps/desktop/README.md` 只列三种连接模式,代码有四种

`apps/desktop/README.md:133 @ 863e313`

> Desktop supports a managed local backend, explicit remote gateways, and Hermes
> Cloud connections. Remote and cloud modes use the same remote-capability path;

代码的 `Mode` 是四元:

`apps/desktop/src/app/settings/gateway-settings.tsx:34 @ 863e313`

```
type Mode = 'local' | 'remote' | 'cloud' | 'ssh'
```

`ssh` 不是残留:它有独立的 ModeCard(`:1095`)、独立的表单区(`:1341`–`:1456`)、独立的连通性测试(`testSsh`,`:912`)、独立的 7 码错误分类,以及主进程侧完整的 `testDesktopConnectionConfig` ssh 分支(`apps/desktop/electron/main.ts:7754`)。
**记 ◎ 不记 ▲**:原句没有"仅""只有"这类封闭词,字面为真,只是显著保守(漏了四分之一的连接模式,而且漏的那种正是执行边界最不同的一种)。

### ◇-1 `subscription.upgrade`:网关有、TUI 用、桌面从不调用

网关声明:`tui_gateway/methods_session.py:2125`:`@method("subscription.upgrade")`
TUI 调用:`ui-tui/src/app/slash/commands/subscription.ts:135`:`.rpc<SubscriptionUpgradeResponse>('subscription.upgrade', {`
共享包为它专门定了类型:`apps/shared/src/billing-types.ts:347`:`export interface SubscriptionUpgradeResponse {`
桌面:`BillingApi` 的 9 个方法里没有它(§2.5 探针输出)。桌面的升级一律 deep-link 门户(`apps/desktop/src/app/settings/billing/use-billing-state.ts:532` 的 `Choose ↗`)。

搜索面:`grep -rn "SubscriptionUpgradeResponse\|subscription.upgrade" --include=*.ts --include=*.tsx apps/ ui-tui/ web/`(排除 node_modules),9 处命中,`apps/` 下只有 `apps/shared/` 的类型定义与转出,`apps/desktop/` 零命中。

### ◇-2 R8A 的 856 键表覆盖不到桌面设置面在用的 3 个键

三个键、三种不同的"表外"成因(逐条给出真实归属):

| 键 | 真实定义处(锚点 + 摘录) | 为什么 R8A 表没有 |
|---|---|---|
| `model_context_length` | `hermes_cli/web_server.py:872`:`"model_context_length": {` | **Web 端合成键**,由 `_normalize_config_for_web` 造、`_denormalize_config_from_web` 折回,从不进 `DEFAULT_CONFIG` |
| `agent.personalities` | `cli.py:481`:`"personalities": {` | 住在 `cli.py::load_cli_config()` 的**另一棵默认树**里,不在 `hermes_cli/config_defaults.py::DEFAULT_CONFIG` |
| `agent.reasoning_effort` | `cli.py:479`:`"reasoning_effort": "",` | 同上 |

R8A 资产是用 AST 从 `DEFAULT_CONFIG` / `OPTIONAL_ENV_VARS` 字面量抽的(`scripts/config_table.py`),因此它的口径是"`DEFAULT_CONFIG` 里的键",不是"运行时合法的键"。这不是 R8A 的错误,但**是一条必须写进资产说明的口径边界**——否则下一轮拿它当"全仓配置键全集"用就会漏。

### ◇-3 三处面板整页脱离 i18n(与 ▲-2 同源,单列是因为它们不在 Billing 里)

`apps/desktop/src/app/settings/custom-endpoints-settings.tsx`(0 处 `useI18n`,18 处字面文案)、
`apps/desktop/src/app/settings/uninstall-section.tsx`(14 处)、
`apps/desktop/src/app/settings/computer-use-panel.tsx`(10 处)。
三者都是可从设置面直达的正式界面(Providers→Custom endpoints / About→Danger zone / Capabilities→Computer Use)。

### ◇-4 `RowValue` 的 `onAction` 无调用方

`apps/desktop/src/app/settings/billing/account-row-value.tsx:9`:`export function RowValue({ onAction, row }: { onAction?: () => void; row: BillingAccountRowView }) {`
搜索面:`grep -rn "<RowValue" apps/desktop/src/`,2 处命中(`billing/index.tsx:142`、`billing/auto-reload-row.tsx:136`),**均未传 `onAction`**。所以 `:37` 那条三元的中间分支是死代码。

---

## 6. 缺陷(■)

### ■-1 幂等键复用:共享 policy 上的标记零消费者,桌面自造的集合少两个码 → 重试可能重复扣款

共享包为此定义了一个专门的标记位:

`apps/shared/src/billing-policy.ts:3 @ 863e313`

```
export type BillingRecovery = 'login' | 'none' | 'portal' | 'reconnect' | 'retry' | 'step_up'

export interface BillingRefusalPolicy {
  recovery: BillingRecovery
  ambiguousMidPoll?: true
  reuseIdempotencyKey?: true
}
```

它被打在 **5 个**码上:`endpoint_unavailable`(:15)、`network_error`(:24)、`rate_limited`(:28)、`stripe_unavailable`(:33)、`temporarily_unavailable`(:34)。

**全仓没有任何一个读取点。** 搜索面(git 跟踪文件全量,无扩展名与目录过滤):

```verify
cd /home/user/hermes-agent && git grep -n "reuseIdempotencyKey" -- .
```

6 处命中,**全部在声明文件 `apps/shared/src/billing-policy.ts` 内部**(1 处字段声明 + 5 处字面量)。

桌面自己重造了一份判据,而且是硬编集合:

`apps/desktop/src/app/settings/billing/use-charge-poller.ts:56 @ 863e313`

```
const retryableSendKinds = new Set([
  'endpoint_unavailable',
  'rate_limited',
  'temporarily_unavailable',
  'timeout',
  'transport'
])
```

`apps/desktop/src/app/settings/billing/use-charge-poller.ts:270 @ 863e313`

```
function shouldReuseIdempotencyKey(refusal: BillingRefusal): boolean {
  return retryableSendKinds.has(refusal.kind)
}
```

两个集合的**线上码**部分:policy = {endpoint_unavailable, network_error, rate_limited, stripe_unavailable, temporarily_unavailable};桌面 = {endpoint_unavailable, rate_limited, temporarily_unavailable}(另加两个客户端侧的 `timeout`/`transport`,那两个是对的)。**缺 `network_error` 与 `stripe_unavailable`。**

后果沿链 B 走一遍:

`apps/desktop/src/app/settings/billing/use-charge-poller.ts:220 @ 863e313`

```
        retryIntentRef.current = shouldReuseIdempotencyKey(chargeResult.refusal)
          ? { amountUsd, idempotencyKey: chargeResult.idempotencyKey }
          : null
```

`apps/desktop/src/app/settings/billing/errors.ts:119 @ 863e313`

```
    case 'stripe_unavailable':
      return {
        action: { type: 'retry' },
        message: stripeRetryMessage(refusal),
        title: 'Stripe is having trouble'
      }
```

`stripe_unavailable` 被映射成 `action: { type: 'retry' }`,**页面会给用户一个 Retry 按钮**;点它 → `flow.start(clampedAmount)` → `retryIntentRef.current` 是 `null` → `idempotencyKey === undefined` → `apps/desktop/src/app/settings/billing/api.ts:147` 现铸一个新 UUID。也就是说:**"Stripe 出问题了,重试一下"这条按钮,发出去的是一笔幂等键全新的请求**。如果第一笔其实已在服务端落地,这就是重复扣款。`network_error` 同理(它连 Retry 按钮都没有,见 ■-5,用户只能再点 Buy,结果一样)。

修法只需一行:该模块 `:1` 已经 `import { refusalPolicy } from '@hermes/shared/billing-policy'`,并在 `:111` 用它读 `ambiguousMidPoll`——把 `shouldReuseIdempotencyKey` 改成 `refusalPolicy(refusal.kind).reuseIdempotencyKey === true`(再并上 `timeout`/`transport`)即可。

网关侧的注释恰好证明这个约定是有意为之的:`tui_gateway/methods_session.py:2183` 把 key 回显进错误信封,注释写 `# so the TUI can reuse on retry`。

### ■-2 保存凭据后的本地乐观遮罩比服务端弱:9–11 字符的密钥会露出其中 8 个

服务端遮罩:短于 `floor`(默认 12)的值**整体**打成 `***`。

`agent/redact.py:482 @ 863e313`

```
    if not value:
        return empty
    if len(value) < floor:
        return placeholder
    return f"{value[:head]}...{value[-tail:]}"
```

`hermes_cli/web_server.py:7053` 的 `redacted_value` 走 `hermes_cli/config.py:4184` 的 `redact_key`,后者就是 `mask_secret(key, empty=…)`,`floor=12` 未被覆盖。

桌面在保存成功后**不重新拉取**,而是本地算一个遮罩顶上去:

`apps/desktop/src/app/settings/helpers.ts:26 @ 863e313`

```
export const redactedValue = (v: string) => (v.length <= 8 ? '••••' : `${v.slice(0, 4)}...${v.slice(-4)}`)
```

`apps/desktop/src/app/settings/env-credentials.tsx:102 @ 863e313`

```
      patchVar(key, { is_set: true, redacted_value: redactedValue(value) })
```

两者的门槛不同:服务端是 `< 12 → ***`,桌面是 `<= 8 → ••••`。**长度 9、10、11 的值落在中间地带**:服务端会返回 `***`,桌面本地却渲染成 `abcd...wxyz` —— 对一个 9 字符的密钥,这是把 9 个字符里的 8 个直接显示出来。这个错误遮罩会一直挂到该页面下一次 mount(`useEnvCredentials` 的 `getEnvVars` 只在挂载时跑一次,`apps/desktop/src/app/settings/env-credentials.tsx:63`–`:80`),期间截图、录屏、共享屏幕都会带上它。

9–11 字符的凭据在本仓不是假想:`category === 'setting'` 下有大量非 API-key 的短值(端口、用户名、代理地址),而 `isKeyVar` 会把任何以 `_KEY`/`_TOKEN`/`_API_KEY` 结尾的名字都当密钥渲染。

### ■-3 `useEnvCredentials` 的 reveal 通道与 `filterEnv` 是死路径

hook 把 `revealed` 与 `onReveal` 一起放进 `rowProps`:

`apps/desktop/src/app/settings/env-credentials.tsx:176 @ 863e313`

```
    vars,
    rowProps: {
      edits,
      revealed,
      saving,
      setEdits,
      onSave: handleSave,
      onClear: handleClear,
      onReveal: handleReveal
    }
  }
```

而 `rowProps` 的唯一最终消费者 `KeyField` 只解构 5 个字段,**`revealed` 与 `onReveal` 都不在其中**:

`apps/desktop/src/app/settings/credential-key-ui.tsx:60 @ 863e313`

```
  const { edits, onClear, onSave, saving, setEdits } = rowProps
```

搜索面:`grep -rn "useEnvCredentials\|rowProps" apps/desktop/src --include=*.ts --include=*.tsx`,`useEnvCredentials` 只有 2 个调用方(`apps/desktop/src/app/settings/providers-settings.tsx:342`、`apps/desktop/src/app/settings/keys-settings.tsx:33`),两者都把 `rowProps` 原样交给 `ProviderKeyRows` / `CredentialKeyCard`,而这两者又只把它转给 `KeyField`。**结论:Settings→Providers 与 Settings→Keys 两页永远不会调用 `POST /api/env/reveal`。** 明文回显能力实际只存在于 `toolset-config-panel.tsx`(它自己维护 `revealed` 局部 state,`:92`/`:146`/`:190`)。

同文件的 `filterEnv` 同样零调用方,而它的注释宣称自己是共享的:

`apps/desktop/src/app/settings/env-credentials.tsx:13 @ 863e313`

```
// Shared filter used by every credential surface (Providers + Keys pages):
// category gate first, then a free-text match across key name + description.
export function filterEnv(info: EnvVarInfo, key: string, q: string, cat: string, extra?: string): boolean {
```

搜索面:`grep -rn "filterEnv" apps/desktop/src --include=*.ts --include=*.tsx` → 1 处命中,即定义本身。Providers 页现在用自己的 `haystack.some(...)`(`apps/desktop/src/app/settings/providers-settings.tsx:447`–`:452`),Keys 页根本没有搜索框。
**严重度**:低(不影响行为),但注释在**断言一个不成立的不变量**,是下一个读代码的人最容易被带偏的形态。

### ■-4 `formatMoney` 有两份实现,一份钉了 `en-US`、一份没钉,而买点数的金额走没钉的那份

`use-billing-state.ts` 的私有版本明确钉死 en-US,并且在注释里写了理由:

`apps/desktop/src/app/settings/billing/use-billing-state.ts:824 @ 863e313`

```
  // Pin en-US so the symbol is always "$" — the server's *_display strings
  // ("$996.47") sit next to these, and other locales render USD as "US$".
  return new Intl.NumberFormat('en-US', {
```

`billing-amounts.ts` 的导出版本没有:

`apps/desktop/src/app/settings/billing/billing-amounts.ts:117 @ 863e313`

```
  return new Intl.NumberFormat(undefined, {
    currency: 'USD',
    maximumFractionDigits: amount % 1 === 0 ? 0 : 2,
    minimumFractionDigits: amount % 1 === 0 ? 0 : 2,
    style: 'currency'
  }).format(amount)
```

`billing/index.tsx:26` 导入的是**没钉的那一份**,用在两处直接面向用户的金额上:`:162`(预设金额 chip 的兜底标签)与 `:270`(充值成功后的"$X added.")。在 `fr-FR`/`de-DE` 这类 locale 下,同一屏里上方摘要卡是 `$996.47`(钉死版),下方成功提示是 `996,47 $`(未钉版)——正是那条注释想避免的现象。

两份 `parseAmount` 也不一致:

`apps/desktop/src/app/settings/billing/billing-amounts.ts:19 @ 863e313`

```
export function parseAmount(value?: null | number | string): null | number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  if (typeof value !== 'string') {
    return null
  }

  const parsed = Number(value.replace(/[$,\s]/g, ''))

  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}
```

`apps/desktop/src/app/settings/billing/use-billing-state.ts:803 @ 863e313`

```
function parseAmount(value?: null | number | string): null | number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }

  if (typeof value !== 'string') {
    return null
  }

  const parsed = Number(value.replace(/[$,\s]/g, ''))

  return Number.isFinite(parsed) ? parsed : null
}
```

前者要求 `parsed > 0`,后者不要求(它需要负数来渲染"超支 $X")。这一处分叉是**有意的**,locale 那一处不是。
另有一处不对称:数字入口两者都放行 `0`(`Number.isFinite(0)` 为真),字符串入口前者会把 `'0'` 判成 `null`——同一个逻辑零,按 wire 上是数字还是字符串会渲染成 `$0` 或 `—`。

### ■-5 桌面拒绝文案表不是编译期穷尽的,8/24 个码退化成通用文案且丢掉 recovery 动作

`apps/shared/src/billing-types.ts:59`–`:66` 的注释明说闭集的目的是"分类表/文案表/测试用 `Record<KnownBillingRefusalCode, …>` 就能在漏映射时编译不过"。`apps/shared/src/billing-policy.ts:11` 照做了(`Record<KnownBillingRefusalCode, BillingRefusalPolicy>`),桌面的文案表**没有**——它是一个带 `default` 的普通 `switch`:

`apps/desktop/src/app/settings/billing/errors.ts:156 @ 863e313`

```
    default:
      return {
        action: { type: 'none' },
        message: refusal.message || 'Billing request failed.',
        title: 'Billing request failed'
      }
```

结果(§2.6 逐码表):**8 个码没有专属文案**,而且更要紧的是 **`action` 一律退化成 `{type:'none'}`**,与共享 policy 的 `recovery` 不一致:

| 码 | policy.recovery | 桌面实际 action | 用户看到的 |
|---|---|---|---|
| `network_error` | `retry` | `none` | 没有 Retry 按钮 |
| `internal_error` | `retry` | `none` | 没有 Retry 按钮 |
| `auto_top_up_disabled_failures` | `portal` | `none` | 没有"打开门户"入口 |
| `idempotency_key_required` / `invalid_charge_id` / `invalid_request` / `preview_rejected` / `validation_failed` | `none` | `none` | 一致(仅文案通用) |

即 **3 个码的恢复路径被吞掉**,5 个只是文案泛化。修法同样廉价:`resolveRefusal` 的 `default` 分支可以回落到 `refusalPolicy(refusal.kind).recovery` 去生成 action。

### ■-6 `apps/shared/src/skill-scaffold.test.ts` 不被任何 vitest project 收集

`apps/shared` 的 `package.json` 只有 `lint / lint:fix / fix / typecheck / check` 五个脚本,**没有 `test`**,devDependencies 里也没有 `vitest`:

`apps/shared/package.json:14 @ 863e313`

```
  "scripts": {
    "lint": "eslint src/",
    "lint:fix": "eslint src/ --fix",
    "fix": "npm run lint:fix",
    "typecheck": "tsc -p . --noEmit",
    "check": "npm run typecheck && npm run lint"
  },
  "devDependencies": {
    "typescript": "6.0.3"
  }
```

**负结论的搜索面**(逐项写出):

1. `find . -name "vitest.config.*" -not -path "*/node_modules/*"` → 4 个:`tests-js/`、`web/`、`ui-tui/`、`apps/desktop/`。四者的 root 都是各自目录,`apps/shared` 不在任何一个之下。
2. 四个 config 的 include:`tests-js` = `**/*.test.ts`(root=tests-js)、`web` = `src/**/*.test.{ts,tsx}`(root=web)、`ui-tui` 无 include(默认 glob,root=ui-tui,exclude dist/node_modules)、`apps/desktop` 两个 project = `src/**/*.test.{ts,tsx}` 与 `electron/**/*.test.ts` + `scripts/**.test.{ts,mjs}`(root=apps/desktop)。
3. `grep -rn "vitest" --include=*.yml --include=*.yaml --include=*.sh --include=*.py --include=*.json .`(排除 node_modules 与 package-lock)→ 只有 4 个包声明 `"test": "vitest run"`:`tests-js`、`web`、`ui-tui`、`apps/desktop`。
4. `.github/workflows/*.yml` 里 `grep -rn "vitest"` → **零命中**。
5. 根 `package.json` 无 `test` 脚本;唯一的聚合脚本是 `check: npm run --ws check`,对 `apps/shared` 展开成 `tsc --noEmit && eslint`。

两次实测确认:

```console
$ cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui ../shared/src/skill-scaffold.test.ts
 RUN  v4.1.10 /home/user/r10b-ts/hermes-agent/apps/desktop
No test files found, exiting with code 1
filter: ../shared/src/skill-scaffold.test.ts
projects: ui
|ui|
include: src/**/*.test.{ts,tsx}
exclude:  **/node_modules/**, **/.git/**

$ cd /home/user/r10b-ts/hermes-agent/ui-tui && npx vitest list | grep -c skill-scaffold
0
```

所以这 61 行、覆盖 `skillInvocationText` 全部分支(单 skill / bundle / 带指令 / 不带指令)的规格,**在 CI 与本地任何一条命令下都不会被执行**。
对照:同目录的 `apps/shared/src/billing-payment-method.test-d.ts` 是**类型层**守卫,`tsc -p . --noEmit` 会覆盖它,所以那一个是有效的;只有需要真跑的那个是死的。

---

## 7. 测试(行为规格)

环境:主线在基线之外准备的 `git archive` 副本 `/home/user/r10b-ts/hermes-agent`,未装任何新包。

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop
npx vitest run --project ui \
  src/app/settings src/app/profiles src/app/gateway/hooks \
  src/lib/gateway-ws-url.test.ts src/lib/json-rpc-gateway-url-guard.test.ts
```

```console
 Test Files  32 passed (32)
      Tests  296 passed (296)
   Duration  93.23s
```

**passed 296 / failed 0 / skipped 0。**

**零执行与整文件跳过的点名**:

```verify
cd /home/user/r10b-ts/hermes-agent
grep -rn "describe\.skip\|it\.skip\|test\.skip\|\.todo(" \
  apps/desktop/src/app/settings apps/desktop/src/app/profiles \
  apps/desktop/src/app/gateway/hooks apps/shared/src
```

零命中——上述 32 个文件内**没有**任何 `.skip` / `.todo`,296 个用例全部真跑。

但**片内有一个整文件零执行**,且它不在上面 32 个文件里,因为根本没有 runner 会收集它:
`apps/shared/src/skill-scaffold.test.ts`(61 行)。它掩盖了多少用例?文件里 3 个 `describe`(见 ■-6 的取证),被掩盖的断言全部针对 `apps/shared/src/skill-scaffold.ts` 这一个片内文件。**这是本片唯一的零执行点。**

覆盖到本片的 32 个文件清单(按目录):

- `apps/desktop/src/app/gateway/hooks/`:`gateway-hmr-survivor.test.ts`、`use-gateway-boot.test.tsx`、`use-gateway-request.test.ts`
- `apps/desktop/src/app/profiles/`:`index.test.tsx`
- `apps/desktop/src/app/settings/`:`fallback-models-field.test.tsx`、`gateway-settings.test.ts`、`gateway-settings.test.tsx`、`helpers.test.ts`、`model-settings.test.tsx`、`providers-settings.test.tsx`、`searchable-select.test.tsx`、`ssh-host-selection.test.ts`、`terminal-backend-panel.test.tsx`、`terminal-font-setting.test.tsx`、`toolset-config-panel.test.tsx`、`voice-field-visible.test.ts`、`voice-provider-fields.test.ts`、`with-active.test.ts`
- `apps/desktop/src/app/settings/memory/`:`provider-config-modal.test.tsx`、`provider-config-panel.test.tsx`
- `apps/desktop/src/app/settings/billing/`:`api.test.ts`、`errors.test.ts`、`index.test.tsx`、`simulated-api.test.ts`、`tier-art.test.ts`、`types.test.ts`、`use-billing-state.test.ts`、`use-charge-poller.test.ts`、`use-step-up.test.tsx`、`use-subscription-change.test.tsx`
- `apps/desktop/src/lib/`:`gateway-ws-url.test.ts`、`json-rpc-gateway-url-guard.test.ts`(测的是 `apps/shared/src/websocket-url.ts` 与 `json-rpc-gateway.ts`,是本片共享包的真实规格所在)

**行为规格里值得记的两条**:`apps/desktop/src/lib/json-rpc-gateway-url-guard.test.ts` 钉住了 `connect()` 对非法 URL 的拒绝——

`apps/shared/src/json-rpc-gateway.ts:101 @ 863e313`

```
    // Refuse garbage; WebSocket coerces non-strings into
    // `ws://<origin>/[object%20Object]` (#68250 stale-emit boot loop).
    const invalidUrl = () => {
      const got = typeof wsUrl === 'string' ? JSON.stringify(wsUrl) : `type "${typeof wsUrl}"`

      return new Error(`gateway connect() requires a ws:// or wss:// URL string, got ${got}`)
    }
```

`apps/desktop/src/lib/gateway-ws-url.test.ts` 钉住了"OAuth 不回落缓存 URL、token 可以"这条 §4.1 的不变量。**共享包的规格住在消费方仓里,而不是包自己里**——这正是 ■-6 的结构性成因。

---

## 8. 判据自查

| # | 判据 | 自评 |
|---|---|---|
| **1 点名到位** | 每个文件全路径 + 一句话角色 | **达标**。§0 七张表覆盖 3+4+11+24+4+19+12 = 77 个文件,全部写全路径 |
| **2 接缝穷举** | 逐项列全、给枚举命令与条数 | **达标(有一处自限)**。已穷举:导航面 17 视图 / 9 参数、config 键 96+5、env 4 路由 + 3 分流、Electron 桥 36 成员、网关 RPC 10 声明 vs 9 调用 + 1 事件、拒绝码 24 逐码对齐、`@hermes/shared` 5 子路径 × 消费方、设备本地 25 store。**自限**:`constants.ts` 的 `PROVIDER_GROUPS`(31 条)、`ENUM_OPTIONS`(21 键)、`FIELD_LABELS`/`FIELD_DESCRIPTIONS` 我只报了条数、没有逐条列出——它们是纯展示数据表,逐条列出对"重实现"没有增益,但按判据字面这是**没做满**,如实记 |
| **3 端到端链** | 逐跳带锚点 | **达标**。链 A 6 跳(组件→回调→状态→纯函数→REST→Python 深合并)、链 B 7 跳(按钮→状态机→API→传输→JSON-RPC→Python handler→共享结算机) |
| **4 逐字取证** | ≥2 个围栏块是逐字源码 | **达标**,共 26 个逐字围栏块(含 3 个 Python、1 个 JSON) |
| **5 记号** | ≥1 条带锚点 | **达标**:■×6、▲×2、◎×1、◇×4 |

**未达标处如实声明**:判据 2 的展示型数据表(`PROVIDER_GROUPS` / `ENUM_OPTIONS` / 两张文案表)只报条数未逐条列全,约占本片接缝总量的一成。其余八张接缝表均为全量。

**引用关卡自测**(主线复核前的自报,重跑口令与实测数):

```verify
cd /home/user/hermes-study
python3 scripts/verify_citations.py /home/user/hermes-agent notes/r10b-raw-settings-billing.md
```

```console
citations=87  OK=61  UNCHECKED=26
可校验比例 OK/87 = 70.1%
table_anchors=42  OK=35  UNCHECKED=7
OK: every code-block-backed citation matches the baseline
```

即 **0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE,退出码 0**,可校验比例 70.1% 刚过 70% 下限。
剩余 26 处 UNCHECKED 全部是散文里的区域指路(「见某文件某行附近」),不是块后锚点——本文件所有代码块的锚点一律写在块**之前**。

---

## 9. 移交项

每条 = 锚点(后紧跟反引号摘录)+ 一句话现象。

| id | 锚点 + 摘录 | 现象 | 建议归属 |
|---|---|---|---|
| **H-R10B-C-a** | `apps/shared/src/billing-policy.ts:8`:`reuseIdempotencyKey?: true` | 该标记全仓零读取点(`git grep` 6 命中全在本文件),而桌面自造的 `retryableSendKinds` 少了 `network_error` 与 `stripe_unavailable` 两个码 → Stripe 故障后点 Retry 会用**新**幂等键重发扣款请求 | ■,建议 R11 章节收进"共享策略表与各界面实现的一致性"一节 |
| **H-R10B-C-b** | `apps/desktop/src/app/settings/billing/use-charge-poller.ts:56`:`const retryableSendKinds = new Set([` | 同上的具体落点;修法是改用 `refusalPolicy(...).reuseIdempotencyKey` | 同上 |
| **H-R10B-C-c** | `apps/desktop/src/app/settings/helpers.ts:26` 的 `redactedValue` | 客户端乐观遮罩门槛 `<=8`,服务端 `mask_secret` 门槛 `<12`;长度 9–11 的凭据保存后会在页面上显示其中 8 个字符,直到下次 mount | ■,凭据处理专题 |
| **H-R10B-C-d** | `apps/desktop/src/app/settings/env-credentials.tsx:184`:`onReveal: handleReveal` | `revealed`/`onReveal` 挂进 `rowProps` 但 `KeyField` 从不解构 → Settings 的 Providers/Keys 两页永不调用 `POST /api/env/reveal`;同文件的 `filterEnv` 也零调用方,而它的注释自称"每个凭据面共用" | ■(低危),但注释断言了一个不成立的不变量 |
| **H-R10B-C-e** | `apps/desktop/src/app/settings/billing/errors.ts:23` 的 `resolveRefusal` | 普通 `switch` + `default`,非编译期穷尽;24 个线上码里 8 个落 default,其中 3 个(`network_error`/`internal_error`/`auto_top_up_disabled_failures`)因此丢掉了 policy 上写明的 retry / portal 恢复动作 | ■ |
| **H-R10B-C-f** | `apps/shared/src/skill-scaffold.ts:46`:`export function skillInvocationText(text: string): null | string {` | 它的规格文件 `apps/shared/src/skill-scaffold.test.ts` 不被任何 vitest project 收集(`apps/shared` 无 test 脚本、无 vitest 依赖、不在四个 config 的 root 下);实测 `No test files found` | ■,测试基建 |
| **H-R10B-C-g** | `apps/desktop/src/app/settings/billing/billing-amounts.ts:110`:`export function formatMoney(value?: null | number | string): string {` | 与 `apps/desktop/src/app/settings/billing/use-billing-state.ts:817` 的同名私有函数是两份实现;后者钉死 `en-US` 并写明理由,前者用运行时 locale,而 Billing 页的"$X added."与预设 chip 走的是前者 | ■ |
| **H-R10B-C-h** | `website/docs/user-guide/cli.md:231`:`personalities:` | 文档 YAML 例子把 personalities 写在**顶层**;CLI / 网关 / TUI / 桌面四处运行时全部读 `agent.personalities`;顶层键在 `_OPEN_DICT_TOP_LEVEL_KEYS` 里所以校验通过、然后永远没人读 | ▲,且与 `features/personality.md:214` 自相矛盾 |
| **H-R10B-C-i** | `apps/desktop/README.md:133`:`Desktop supports a managed local backend, explicit remote gateways, and Hermes` | 只列三种连接模式,代码是四种(`apps/desktop/src/app/settings/gateway-settings.tsx:34` 的 `ssh`),而 ssh 恰是执行边界最不同的一种 | ◎(字面为真但显著保守) |
| **H-R10B-C-j** | `apps/shared/src/billing-types.ts:143`:`export type BillingPaymentMethod =` | 类型注释明说 "`!card` 不等于没有支付方式",但桌面 `deriveBillingView` 的三处判断(`noCardNotice`/`paymentMethodRow`/`buyCreditsRow`)**只看 `billing.card`**;对 Link 客户会显示"No payment method on file"并禁用 Buy。**未定性**:老网关会整字段缺席,缺席时只能看 `card`,需要先确认网关版本矩阵才能判是不是缺陷 | 待定,需 R11 与网关侧一并判 |
| **H-R10B-C-k** | `hermes_cli/web_server.py:872`:`"model_context_length": {` | `data/r8a-config-keys.tsv`(856 键)的口径是 `DEFAULT_CONFIG` 字面量,覆盖不到 Web 合成键与 `cli.py::load_cli_config()` 的另一棵默认树;桌面设置面用到的 101 个键里有 3 个在表外 | ◇,建议在 R8A 资产说明里补一句口径边界 |
| **H-R10B-C-l** | `apps/desktop/DESIGN.md:285`:`- Every user-facing string goes through \`useI18n()\` (\`src/i18n/context.tsx\`).` | 全称句被证伪:整个 Billing 页(含 `errors.ts` 18 条文案)、`uninstall-section.tsx`、`custom-endpoints-settings.tsx`、`computer-use-panel.tsx` 全是硬编英文 | ▲ |

---

## 10. 本片成本自报

```text
片号            : C
层              : L2
文件数 / 行数   : 77 / 19,070
实际打开的文件数: 77          (全部真读过内容;其中 model-settings.tsx / pet-settings.tsx /
                              dev-fixtures.ts / toolset-config-panel.tsx 四个长文件是
                              「接口面全读 + 实现体分段抽读」,符合 L2 口径)
实际读过的行数  : ≈15,500     (估法:19,070 减去四个长文件中未逐行读的部分——
                              model-settings 约 1,080 行、pet-settings 约 330 行、
                              dev-fixtures 约 400 行、gateway-settings 的样式段约 700 行、
                              其余零散 JSX 样式约 1,000 行)
底稿字节数      : (主线自测)
主观耗费        : 中偏高。瓶颈是**跨文件追链 + 跨语言对账**,不是文件数也不是单文件长度:
                  三处最花时间的都是"要跨到片外才能定性"——(a) 桌面 96 个 config 键要
                  跟 R8A 的 Python 侧 856 键表逐个对,才发现 3 个表外键各有不同成因;
                  (b) 幂等键缺陷要从 use-charge-poller 一路追到 tui_gateway 的 handler
                  注释才能确认约定是有意的;(c) personalities 的 ▲ 要同时看
                  config_defaults.py、cli.py、四个运行时读取点和两页互相矛盾的文档。
                  纯"读接口面"的部分(19 个 billing 文件、12 个 shared 文件)反而很快。
```

**SLICE C COMPLETE 的前置检查**:基线工作区干净。

```verify
git -C /home/user/hermes-agent status --porcelain
git -C /home/user/hermes-agent rev-parse HEAD
```

实测:`status --porcelain` 空输出;HEAD = `863e31318553cda8ad61df681d08175364d4164b`。
