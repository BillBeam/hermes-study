# r11c 底稿 · 片 A —— 案号重复造成的隐形欠账

> 溯源约定:凡对 hermes-agent 的断言,锚点写作 `路径:行号 @ 863e313`,**单独成行、置于代码块之前**。
> 对本学习仓库自身产出(`notes/` `reports/` `data/`)的引用,锚点为 `路径:行号`(无 `@` 后缀),
> 因为它们随本仓库演进、不属于只读基线。

## 任务范围

R11B 发现「同一案号指多件事」这个物种:39 个移交号对应 100 个实体,人工核实真撞号 35。
本片两件事:

1. **(优先,必须完成)** 结清 `H-R11B-A-c` 与 `H-R11B-A-d` —— `H-R10B-a` 被三处独立铸号,
   R11A 只结清了第一处,另两处从未处置且因号已标结清而不会再被发现。逐条取证给处置结论。
2. 对 35 处真撞号逐一追查是否还有同类后果(某一处铸号被标结清、同号的另一处从未被处置),
   并复核 39/35 的差与 R11B 自陈的「至少 1 个漏报」,报出本片自己的读数。

**产出文件**:本底稿 + `data/r11c/a-id-collisions-*`。

---

<!-- 增量写入起点:以下各节按完成顺序追加 -->

## §1 结清 `H-R11B-A-c` —— pet 的 profile 作用域在客户端与服务端各缺一半

**结论(先写):现象属实,而且比原记录更重。** 判 **■(中高)**,新立 `■-R11C-A-01`;
不记 ▲(与文档无关,是代码内部不一致)。原记录说的是「服务端 `pet.generate` 少了
`@_profile_scoped`」——这一半为真;但**它不是近因**:桌面端 `pet-generate.ts` 里
11 条 pet RPC 调用**全部绕过**了同目录 `pet-gallery.ts` 那个「一个收口点,谁都别忘」的
`petRpc` 收口,该文件里 `profile` 一词**出现 0 次**。于是即便把装饰器补上也**不改变任何行为**,
因为 `_profile_scoped` 是靠 `params["profile"]` 生效的,而客户端根本没送这个参数。
**真正可复述的后果是:同一个「领养」动作有两条路径,一条落在聚焦 profile、一条落在启动 profile。**

### 1.1 原记录与它的两处铸号

`notes/r10-raw-tui-gateway-methods.md:1648` 与 `notes/r11b-raw-rulings-census.md:883`

> | H-R10B-a | `tui_gateway/methods_session.py:1800`:`@method("pet.generate")` | 该行下一行直接是 `def _(rid, params: dict) -> dict:`,**没有** `@_profile_scoped`;而 `pet.info`(`:1326`)、`pet.gallery`(`:1480`)等 12 个方法都有 —— 于是 `pet.hatch` 把宠物装进启动 profile,`pet.gallery` 从聚焦 profile 读,新宠物看不见 | 读 `agent/pet/generate/__init__.py` 的 `hatch_pet` 确认落盘点;若确认,这是一条可直接提 issue 的缺陷 |

### 1.2 服务端:15 个 pet 方法里 4 个未加作用域装饰器

```verify
awk '/^@method\("pet\./{m=$0; getline nx; printf "%-22s %s\n", substr(m,9,length(m)-9), (nx=="@_profile_scoped" ? "scoped" : "UNSCOPED")}' /home/user/hermes-agent/tui_gateway/methods_session.py
```

```text
"pet.info"             scoped
"pet.info.meta"        scoped
"pet.cells"            scoped
"pet.gallery"          scoped
"pet.select"           scoped
"pet.remove"           scoped
"pet.export"           scoped
"pet.rename"           scoped
"pet.thumb"            scoped
"pet.disable"          scoped
"pet.scale"            scoped
"pet.cancel"           UNSCOPED
"pet.generate.status"  UNSCOPED
"pet.generate"         UNSCOPED
"pet.hatch"            UNSCOPED
```

原记录说「12 个方法都有」——**按本口径是 11 个 pet 方法有**。第 12 个
`@_profile_scoped` 装的不是 pet 方法,是编码校验证据那个 handler:

`tui_gateway/methods_session.py:282 @ 863e313`

```python
@_profile_scoped
def _(rid, params: dict) -> dict:
    """Best known coding verification evidence for a cwd/session.
```

未加的是 4 个而不是 1 个:`pet.cancel` / `pet.generate.status` / `pet.generate` / `pet.hatch`。
**原记录只点了 `pet.generate` 一个,漏了同批的 `pet.hatch` —— 而它才是真正落盘的那个。**

`tui_gateway/methods_session.py:1800 @ 863e313`

```python
@method("pet.generate")
def _(rid, params: dict) -> dict:
```

`tui_gateway/methods_session.py:1913 @ 863e313`

```python
@method("pet.hatch")
def _(rid, params: dict) -> dict:
```

对照有装饰器的那一类:

`tui_gateway/methods_session.py:1480 @ 863e313`

```python
@method("pet.gallery")
@_profile_scoped
def _(rid, params: dict) -> dict:
```

### 1.3 装饰器怎么生效:它读的是 `params["profile"]`

`tui_gateway/server.py:1416 @ 863e313`

```python
    def wrapper(rid, params):
        home = _profile_home(params.get("profile") if isinstance(params, dict) else None)
        if home is None:
            return handler(rid, params)
        token = set_hermes_home_override(home)
```

**这就是「补装饰器不解决问题」的原因**:`params` 里没有 `profile` 时 `_profile_home`
返回 `None`,`wrapper` 直接透传,行为与没装饰器**逐字相同**。

落盘点确认(原记录的建议动作):宠物目录由 `get_hermes_home()` 解析,
而 `get_hermes_home()` 正是上面 `set_hermes_home_override` 覆盖的那个。

`agent/pet/store.py:56 @ 863e313`

```python
def pets_dir() -> Path:
    """Return the profile-scoped pets directory (created on demand)."""
    path = get_hermes_home() / "pets"
```

草稿暂存目录同源:

`tui_gateway/server.py:8182 @ 863e313`

```python
def _pet_gen_root():
    """Profile-scoped staging dir for in-progress generation drafts."""
    from hermes_constants import get_hermes_home

    root = get_hermes_home() / "cache" / "pet-gen"
```

### 1.4 客户端:收口点存在,但孵化流水线整条绕过它

`apps/desktop/src/store/pet-gallery.ts:63`

```typescript
const petRpc = <T>(request: GatewayRequest, method: string, params: Record<string, unknown> = {}): Promise<T> =>
  request<T>(method, { ...params, profile: petProfile() })
```

这段注释自称「One chokepoint so no call site can forget it」。**同目录的
`pet-generate.ts` 就是那个 forget it 的 call site**:

```verify
for f in store/pet-generate.ts store/pet-gallery.ts components/pet/floating-pet.tsx; do printf '%-26s rpc_literals=%-3s profile_mentions=%s\n' "$(basename $f)" "$(grep -cE "'pet\.[a-z.]+'" /home/user/hermes-agent/apps/desktop/src/$f)" "$(grep -c profile /home/user/hermes-agent/apps/desktop/src/$f)"; done
```

```text
pet-generate.ts            rpc_literals=13  profile_mentions=0
pet-gallery.ts             rpc_literals=13  profile_mentions=6
floating-pet.tsx           rpc_literals=2   profile_mentions=6
```

`pet-generate.ts` 的 13 处字面量里 11 处是 RPC 调用(另 2 处是
`pet.generate.progress` / `pet.hatch.progress` 事件订阅),**全部**写成裸 `request(...)`。

### 1.5 最锋利的形态:同一个「领养」有两条路径,落在两个 profile

`apps/desktop/src/store/pet-gallery.ts:326`

```typescript
    await petRpc(request, 'pet.select', { slug })
```

`apps/desktop/src/store/pet-generate.ts:616`

```typescript
    const result = await request<{ ok: boolean; slug: string; displayName: string }>('pet.select', {
```

**同一个 `pet.select`、同一个装饰器、同一句 UI 语义(「领养这只宠物」),
从图鉴进入时带 `profile` → 落在聚焦 profile;从蛋孵化界面进入时不带 → 落在启动 profile。**
`pet.select` 的 docstring 写明它会写 `display.pet.*` 配置

`tui_gateway/methods_session.py:1566 @ 863e313`

```python
    """Adopt a pet from the desktop picker: install (if needed) + activate.

    Params: ``slug`` (required). Writes ``display.pet.*`` to config and returns
```

所以在 app-global remote 模式下(一个后端服务所有 profile,聚焦 profile ≠ 启动 profile),
从蛋孵化界面领养会**改掉另一个 profile 的吉祥物配置**,而当前 profile 的悬浮宠物
(`apps/desktop/src/components/pet/floating-pet.tsx:187` 的 `pet.info` 轮询**带** `profile`)
毫无反应 —— 悬浮宠物那条轮询是**带** `profile` 的:

`apps/desktop/src/components/pet/floating-pet.tsx:187 @ 863e313`

```typescript
        const next = await requestGateway<PetInfo>('pet.info', { profile: petProfile() })
```

原记录说的「新宠物看不见」是这条链的下游表现,**成立**。

### 1.6 前置条件与严重性

- **触发前置**:app-global remote 模式 + 聚焦 profile ≠ 启动 profile。
  单 profile / per-profile-remote 部署下 `petProfile()` 解析为启动 profile,
  `_profile_home` 返回 `None`,两条路径重合,**不触发**。
- **不会丢数据**:宠物文件确实写进了启动 profile 的 `pets/`,只是在聚焦 profile 里看不见;
  切回启动 profile 即可见。
- **无测试覆盖**:全仓唯一的 pet.generate 测试文件只有 1 个用例且不涉及 profile。

```verify
grep -c "def test_" /home/user/hermes-agent/tests/tui_gateway/test_pet_generate_rpc.py; grep -c "profile" /home/user/hermes-agent/tests/tui_gateway/test_pet_generate_rpc.py || true
```

```text
1
0
```

**搜索面(负结论「无测试覆盖」)**:`grep -rn '"pet\.hatch"\|"pet\.gallery"\|"pet\.generate"' tests/ --include=*.py`
在基线 `tests/` 下只命中 `tests/tui_gateway/test_pet_generate_rpc.py:22` 一行;
`grep -rn "_profile_scoped" tests/ --include=*.py` 命中 10 处,无一处涉及 pet 方法
(命中的是 config / platform_base / secret_scope / file_safety / web_server /
tui_gateway server 的 mcp 与 agent build / kanban)。排除了 `__pycache__`。

### 1.7 处置结论

| 项 | 结论 |
|---|---|
| 现象是否属实 | **属实**,但原记录给的近因不完整(见 §1.4) |
| 记号 | **■-R11C-A-01**(中高)。不记 ▲/◇/◎ —— 与自绘地图无关 |
| 修法 | 两半都要:(a) `pet-generate.ts` 改走 `petRpc` 收口(或把收口上移到共享模块);(b) `pet.generate` / `pet.hatch` / `pet.cancel` / `pet.generate.status` 补 `@_profile_scoped`。**只做 (b) 是空操作** |
| 是否新立案号 | 是,`■-R11C-A-01`;`H-R11B-A-c` 本身**关闭** |
| 移交 | 不再移交。修法属基线代码变更,不在本学习项目范围;R12 蓝图可作为「收口点靠约定、不靠类型」的反例素材 |


---

## §2 结清 `H-R11B-A-d` —— gateway-pill 默认开启,而且它是**唯一**默认开启的内置插件

**结论(先写):现象属实,静态链已闭合到渲染层,判 **■(中)**,新立 `■-R11C-A-02`。**
比原记录多两点:(a) 三个内置插件里只有 `gateway-pill` 没写 `defaultEnabled`,另外两个
demo 插件都显式写了 `false` —— 这不是「大家都这样」,是**一个漏写**;(b) 这个重复药丸
**在状态栏可见性菜单里根本不出现**(它没有 `toggleLabel`),用户想关掉只能去插件设置里
禁用整个插件。另外顺带发现原轮次漏记的一条**地图级 ▲**(见 §2.5),它与本案同源。

### 2.1 原记录

`notes/r10b-raw-capability-panels.md:1365`

> | **H-R10B-a** | `apps/desktop/src/plugins/gateway-pill/plugin.tsx:350`:`const plugin: HermesPlugin = {` | 该插件未声明 `defaultEnabled`,默认开启,与核心 `gateway-health` 同时渲染两个网关药丸(§6 ■-H-1);**未经运行期验证** | 有 Electron 的轮次跑一次 `e2e/boot.spec.ts` 变体截图核实 |

**运行期验证仍然做不到**(容器无 Electron 二进制,与 R10B 当时相同)。本节做的是把静态链
补到「无法再有别的分支」的程度,并给出它与另外两个内置插件的对照。

### 2.2 三个内置插件,只有它没写 `defaultEnabled`

```verify
for p in /home/user/hermes-agent/apps/desktop/src/plugins/*/plugin.tsx; do printf '%-14s %s\n' "$(basename $(dirname $p))" "$(grep -oE '^  defaultEnabled: (true|false),' $p || echo '(undeclared -> defaults to true)')"; done
```

```text
example          defaultEnabled: false,
gateway-pill   (undeclared -> defaults to true)
kanban           defaultEnabled: false,
```

`apps/desktop/src/plugins/gateway-pill/plugin.tsx:350 @ 863e313`

```typescript
const plugin: HermesPlugin = {
  id: 'gateway-pill',
  name: 'Gateway Pill',
```

「未声明即开启」由发现器写死:

`apps/desktop/src/contrib/plugins.ts:66 @ 863e313`

```typescript
    if (pluginActive(plugin.id, plugin.defaultEnabled ?? true)) {
      activate()
    }
```

**这三个插件是同一批 demo**:`example` 与 `kanban` 的文件头都写着
「Ships OFF by default (`defaultEnabled: false`)」,`gateway-pill` 的文件头写的是
「a plugin can rebuild a REAL core feature through the SDK alone」——同样是演示意图,
唯独少了那一行。

### 2.3 静态链:两个药丸都会进同一条列表,没有任何去重

插件把自己注册进 `statusBar.right`:

`apps/desktop/src/plugins/gateway-pill/plugin.tsx:358 @ 863e313`

```typescript
    ctx.register({
      id: 'pill',
      area: 'statusBar.right',
      order: 90,
      data: {
```

核心那一项在 `use-statusbar-items.tsx` 里硬编码,id 是 `gateway-health`:

`apps/desktop/src/app/shell/hooks/use-statusbar-items.tsx:407 @ 863e313`

```typescript
        id: 'gateway-health',
        label: copy.gateway,
        menuClassName: 'w-72',
        menuContent: gatewayMenuContent,
```

两者在同一个 `useMemo` 里**直接拼接**,无 id 去重、无过滤:

`apps/desktop/src/app/shell/hooks/use-statusbar-items.tsx:597 @ 863e313`

```typescript
  const statusbarItems = useMemo(
    () => [...extraRightItems, ...coreRightStatusbarItems],
    [coreRightStatusbarItems, extraRightItems]
  )
```

**即便有 id 去重也拦不住**:插件项的 `data.id` 是 `'gateway-pill'`,核心项是
`'gateway-health'`,两个不同的 id。所以「重复」是语义重复,不是 id 重复。

### 2.4 比原记录更重的一点:这个重复项关不掉

渲染过滤器对**没有** `toggleLabel` 的项无条件放行:

`apps/desktop/src/app/shell/statusbar-controls.tsx:89 @ 863e313`

```typescript
  const visible = (item: StatusbarItem) =>
    !item.hidden && (item.lockedVisible || !item.toggleLabel || !hiddenIds.includes(item.id))
```

而可见性菜单只列**有** `toggleLabel` 的项:

`apps/desktop/src/app/shell/statusbar-controls.tsx:143 @ 863e313`

```typescript
  const toggles = useMemo(() => {
    const seen = new Set<string>()

    return [...leftItems, ...items].filter(item => {
      if (!item.toggleLabel || seen.has(item.id)) {
        return false
      }
```

插件那一项的 `data` 里没有 `toggleLabel`(§2.3 的块已列全字段:`icon` / `id` / `label` /
`detail` / `menuClassName` / `menuContent` / `variant`),核心项**有**:

`apps/desktop/src/app/shell/hooks/use-statusbar-items.tsx:413 @ 863e313`

```typescript
        toggleLabel: copy.gateway,
        variant: 'menu'
```

于是用户在状态栏右键菜单里只能关掉**真的那个**,关不掉**重复的那个**。

### 2.5 顺带:R10B 的 ▲ 漏了两处同源出处,其中一处在无争议的地图源里

R10B 已把「None ship in-tree today」记为 `▲-H-2`:

`notes/r10b-raw-capability-panels.md:1045`

> ### ▲-H-2 —— `src/plugins/README.md` 说「目前没有内置插件」,实际有三个

并如实标注「`src/plugins/README.md` 不在派工书列的文档来源清单里,由主线决定是否计入」。
**本轮补两处它没查到的同一句话:**

`website/docs/developer-guide/desktop-plugin-sdk.md:62 @ 863e313`

> differences. No desktop plugins ship in the core tree today — reference demos

这一处在 `website/docs/**`,是 CLAUDE.md 明确列为「作者自绘地图」的来源,**无来源等级争议**。
按 CLAUDE.md「整句/整段一并判定」:整句还断言 reference demos 住在 companion 仓库。
**后半句本容器无网络,不可证伪、不主张证伪**(同名插件两边都有是完全可能的);
▲ 只落在「No desktop plugins ship in the core tree today」这半句。

第二处是模块 docstring,按 R11B 定的分线记 **▲(码内)**:

`apps/desktop/src/contrib/plugins.ts:4 @ 863e313`

```typescript
 *  - BUNDLED: every `src/plugins/<name>/plugin.{ts,tsx}` default-exporting a
 *    `HermesPlugin` registers automatically (vite glob — drop a folder in).
 *    None ship in-tree today; reference/demo plugins live in the companion
 *    `hermes-example-plugins` repo.
```

**同一个文件,上两行说「drop a folder in 就会自动注册」,下一行说「树里一个都没有」,
而它自己的 glob 当场匹配三个。**

**不记 ▲ 的一处**:

`AGENTS.md:845 @ 863e313`

> `agent/image_gen_provider.py`. Reference / docs-companion plugins
> (`example-dashboard`, `strike-freedom-cockpit`, `plugin-llm-example`,
> `plugin-llm-async-example`) live in the
> [`hermes-example-plugins`](https://github.com/NousResearch/hermes-example-plugins)
> companion repo, not in this tree.

这段点的是 `example-dashboard` / `strike-freedom-cockpit` / `plugin-llm-example` /
`plugin-llm-async-example` 四个 **dashboard/python 侧**插件,**不是**桌面 bundled 插件。逐个 `find` 只有
`tests/fixtures/plugins/example-dashboard` 一个同名目录(测试夹具,不是发布插件),
**该段断言成立,不记 ▲**。这是「整句一并判定」要防的形状:三处措辞相近的句子里有一处是对的。

### 2.6 处置结论

| 项 | 结论 |
|---|---|
| 现象是否属实 | **属实**。静态链闭合到渲染层;运行期截图仍未做(容器无 Electron),但链上无剩余分支 |
| 记号 | **■-R11C-A-02**(中);另 **▲**(地图级,`website/docs/developer-guide/desktop-plugin-sdk.md:62`)+ **▲(码内)**(`apps/desktop/src/contrib/plugins.ts:4`)。R10B 的 `▲-H-2` 是同一条断言的第三处出处,**不重复计数**,本轮只补出处 |
| 严重性为什么不是「高」 | 纯 UI 重复,无数据风险;但它同时命中「默认开启」与「关不掉」,比单纯多一个药丸重 |
| 修法 | 给 `gateway-pill` 补 `defaultEnabled: false`(与 `example` / `kanban` 对齐),或给它的 `data` 补 `toggleLabel` 让它至少可关 |
| 是否新立案号 | 是,`■-R11C-A-02`;`H-R11B-A-d` 本身**关闭** |

---

## §3 任务二的方法:先把「谁被处置语盖到了」机械化,再逐条人读

**结论(先写):机械化只到「排队」为止,不到「判开闭」。** 本片新增探针
`data/r11c/a-id-collisions-coverage.py` 给每个(案号, 实体)打三档队列标签,
**不自动下结论** —— CLAUDE.md(R11C)刚定过:「机械判据不得用词根去判开/闭这类语义……
判开闭是人的事,普查的事是别让任何一条从眼前消失。」

三档的定义(判据全在探针 docstring 里,此处只说它们各自意味着什么):

| 标签 | 含义 | 对「H-R10B-a 同类后果」意味着什么 |
|---|---|---|
| `NO-RULING` | 该号在全语料**没有任何** STRONG 处置语 | **定义上不可能**发生「随号消失」——没有那句「结清」可供误读 |
| `COVERED` | 有 STRONG 处置语**点名**了这个实体(锚点路径 / 铸号文件 / 同文件邻近三条声明式路径之一) | 该实体被处置过,不是欠账 |
| `REVIEW` | 该号**有** STRONG 处置语,但**没有一条点名这个实体** | ←—— `H-R10B-a` 的形态。**候选,要人读** |

### 3.1 两个读数(必报项:剔除与不剔除本片承载清单)

```verify
python3 data/r11c/a-id-collisions-coverage.py --summary; python3 data/r11c/a-id-collisions-coverage.py --summary --no-census
```

```text
# 语料 8d6bac6 / 276 份  剔除前缀 ('r11c-',)  处置语语料 276 份
# 撞号 39 号 / 100 实体
# 实体标签  NO-RULING=37  COVERED=18  REVIEW=45
# 语料 8d6bac6 / 276 份  剔除前缀 ('r11c-',)  处置语语料 274 份 (--no-census)
# 撞号 39 号 / 100 实体
# 实体标签  NO-RULING=43  COVERED=16  REVIEW=41
```

**两个读数差 6 个实体,原因是本片要测的那个东西被上一轮的报告改写过。**
`H-R10B-a` 的两个实体在**不剔除**读数下都是 `COVERED` —— 点名它们的
「处置语」是 `notes/r11b-raw-rulings-census.md:883` 与 `:884`,
也就是 R11B **把这两条列为未处置欠账**的那两行。R11B 在同一份文件里写的是
「这两条至今没有任何一轮处置过」,而机械判据把「被点名」读成了「被处置」。

**这正是 CLAUDE.md 说的那件事:这类测量对「报告它」这个动作不幂等** ——
写一份点名清单,下一次的读数就变了。所以 `--no-census` 用一份**声明式**的两文件名单
(`CENSUS_FILES`,写死在探针里,不做「看起来像普查」的嗅探)给出第二个读数。
**两个读数都不是唯一真值**:不剔除的把「被清单点名」误算成 COVERED;
剔除的会把 R11B 报告里**真正的**处置也一起剔掉。逐条人读时以正文为准,不以标签为准。

**与 R11B 读数的口径关系**:撞号号数与实体数(39 / 100)与 R11B **完全一致**,
因为铸号判据是 `import` 它的探针得到的,不是重写的。变的只是本片新加的第三个维度
(处置语落在哪个实体上),R11B 没有这个维度。

### 3.2 语料快照为什么钉在 `8d6bac6` 而不是工作区

片 C / 片 D / 片 E / 片 F 与本片**并发**改历史 `notes/`。从工作区读会让本底稿报出的
每个数随它们的进度漂移,而「shell 命令即证据」关卡是在他们改完之后才重跑的。
上一次(批次一)这个 rev 钉的是 `4b215e8`;本次上调到 `8d6bac6`,
因为 `3f9f6ee` 改正了六处历史锚点漂移,从旧 rev 读会让本底稿引用的行号与工作区对不上,
而引用关卡是按**工作区**解析的。

---

## §4 复核 R11B 的 39 / 35 / 「至少 1 个漏报」,并给本片自己的读数

**结论(先写,四条):**

1. **R11B 点名的 4 个误报,逐条读正文,4 个全部属实** —— 它们都是「同一条案子的
   续写/交叉引用」,不是独立铸号。**39 − 4 = 35,这个数本片确认。**
2. **R11B 说的「至少 1 个漏报」属实(就是 `H-R9B-6`),但它给的原因不对。**
   真正的机制不是「锚点写在标题下一行之外被滤掉」——探针**找到了**那条铸号位;
   是那条铸号位的 3 行搜索窗**多吞了一个不相干的锚点**,而实体分组按锚点集相交做,
   于是两条不同的案子被**融成了一个实体**,这个号就不再被报成撞号。
3. **本片自己的读数:真撞号 36 号**(35 + `H-R9B-6`)。同时给两个机械变体的读数
   (窄 span 36 号 / 83 实体、含本仓库锚点 41 号 / 115 实体),**它们都不是真值**,
   各自的偏差在 §4.3 逐项说明。
4. 顺带查出一条新的**锚点不可见**缺口:`.tsv` 不在校验器扩展名白名单上,
   R10B 主线移交表里指向台账的那条锚点因此既不校验也不计数。全语料实测**只有 1 处**,
   铸 `H-R11C-A-a`,如实按 1 处报,不夸大。

### 4.1 四个误报逐条复核(读正文,不看标签)

| 案号 | 被判误报的那个「实体」 | 读到的正文 | 复核 |
|---|---|---|---|
| `H-17` | `notes/r8c-10-h17-env-loader-race.md:17`:`**本轮结论:H-17 成立,定案 ■-R8C-01。三条后果全部在 venv 里实跑复现。**` | 这是 H-17 **定案底稿的结论行**;锚点变成 `gateway/run.py` 是因为结论说「移交项猜的热重载那条路根本不走 `load_hermes_dotenv`」 | **误报属实**。同一条案子的续写 |
| `H-R8C-f` | `notes/r10-raw-web-dashboard.md:1438`:`### 6.2 H-R8C-f —— backup/import 在 `/system` 页,**import 有二次确认、backup 一次点击零警告**` | 这是同一条案子的**前端半边**;`web/src/App.tsx:214` 是「侧栏标签 System 在哪一行」的路由指路,不是新案子 | **误报属实**。R10 报告自己写的是「本轮只结清前端半边」 |
| `H-R8D-e` | `notes/r9a-90-rulings.md:500`:`**(二)`sync.base_url` 那条 ■ 与 H-R8D-e 是同一形状的**另一个实例**,主线独立坐实。**` | 这行**自陈**是「同一形状的另一个实例」,不是给 `H-R8D-e` 铸第二次号 | **误报属实**。交叉引用 |
| `H-R9A-g` | `notes/r9d-92-mainline-tests-and-crosschecks.md:624`:`**一处跨条目的呼应,值得单独指出**:`x_search` 同时是 §H-R9A-g 查出的` | 这行引用的正是 `H-R9A-g` **自己查出的**那 7 个 toolset 之一 | **误报属实**。交叉引用 |

**四条共同的形态**:探针的铸号判据是「行首有案号 + 同一行(或紧邻几行)有可解析锚点」,
它分不出「这里在给案子铸号」和「这里在引用案子」。这是**判据的射程问题,不是 bug**
—— R11B 自己也是这么定性的(「漏报优于误报」),本片同意。

### 4.2 漏报:`H-R9B-6` 属实,但机制与 R11B 写的不同

R9B 的两份底稿各给 `H-R9B-6` 铸了一次号,指两件事:

`notes/r9b-raw-pet.md:1394`

> | H-R9B-6 | `tui_gateway/server.py:8225`:`_pet_cancelled: set[str] = set()` | 生成取消用一个模块级全局 set 存 token,未见清理策略 | 属网关簇,本轮只到边界为止;交给做 `tui_gateway` 的轮次 |

`notes/r9b-raw-voicein.md:1826`

> **H-R9B-6** —— `tools/wake_word.py:1439`:`def feed_audio(*, owner: object, pcm_int16) -> bool:`

**R11B 写的原因是**「voicein 底稿的锚点写在标题下一行之外,被更窄的判据滤掉」。
**实测不是这样**:探针**两条铸号位都找到了**,voicein 那条的锚点集是
`{tools/wake_word.py, tui_gateway/server.py}` —— 多出来的 `tui_gateway/server.py`
来自铸号行**下面第二行**的 `tui_gateway/server.py:13053`(那是「桌面端怎么送 PCM」的
指路,与本案无关)。加粗段首的搜索窗是 3 行,把它吞了进来;而实体分组按**锚点集相交**做,
于是这一条与 pet 底稿那一条被判成了同一个实体。

**所以漏报的成因是「窗口过宽 → 假相交 → 假合并」,不是「窗口过窄 → 漏掉锚点」。
方向正好相反。** 这条更正对下一轮有用:想减少漏报**不能靠放宽窗口**,那只会更多假合并。

### 4.3 两个机械变体的读数(复核用,都不是真值)

```verify
python3 data/r11c/a-id-collisions-underreport.py
```

```text
R11B 口径(基准)            撞号  39 号 / 100 实体
变体A 窄 span             撞号  36 号 /  83 实体
变体B 含本仓库锚点             撞号  41 号 / 115 实体

变体A 新增撞号 1: H-R9B-6
变体A 丢失撞号 4: H-17, H-R8D-e, H-R9A-g, H-R9B-1

变体B 实体数变多的号 11:
  H-1: 4 -> 5 实体
  H-7: 4 -> 5 实体
  H-R10B-a: 2 -> 3 实体
  H-R10B-b: 2 -> 3 实体
  H-R10B-f: 2 -> 3 实体
  H-R10B-g: 2 -> 3 实体
  H-R9A-a: 3 -> 4 实体
  H-R9A-b: 3 -> 4 实体
  H-R9B-1: 2 -> 3 实体
  H-R9B-a: 4 -> 5 实体
  H-R9B-d: 2 -> 3 实体
变体B 新增撞号 2: H-R10-f, H-R8D-c
```

**变体 A(把加粗段首/小节标题的锚点窗从 3–4 行收到 1 行)**:

- 它**独立捞出了 `H-R9B-6`**,与 §4.2 的人读结论一致;
- 它**丢掉的 4 个里有 3 个正好是 R11B 人工核实的误报**(`H-17` / `H-R8D-e` / `H-R9A-g`)
  —— 两条完全独立的路径(一条人读正文、一条改窗口宽度)指向同一批,这是**互证**;
- 但第 4 个 `H-R9B-1` **是真撞号,不是误报**:pet 底稿指 `hermes_cli/pets.py:182` 的
  `--cycle` 状态表,voicein 底稿指 `tools/voice_mode.py` 的 ■-1 收口,两件事。
  它丢失只是因为 voicein 那条的锚点写在加粗行的**下一行**。
  **所以变体 A 是代理指标,不是判决** —— 4 丢里 3 真 1 假。

**变体 B(锚点存在性放宽到「基线或本学习仓库任一」)**:

- 它坐实了 R11B 说的「实体数系统性偏低」:`H-R10B-a` 从 2 涨到 3,
  多出来的正是 R11B 人工核实的第三处铸号 `reports/round-10b-desktop-application.md:702`;
- 但**新增的 2 个撞号(`H-R10-f` / `H-R8D-c`)都是假的** —— 它们的「第二个实体」
  都是 `notes/r11b-raw-rulings-census.md` 里**讨论这个案子**的表格行,
  锚点指向本仓库自己的 `notes/` / `reports/`。**又是 §3.1 那个不幂等问题**:
  上一轮写下的普查清单,变成了这一轮的假铸号位;
- 11 个「实体数变多」里也只有 4 个是真的(`H-R10B-a/b/f/g`,锚点在
  `reports/round-10b-desktop-application.md:702-708` 的 R10B 主线移交表),
  另 7 个(`H-1`、`H-7`、`H-R9A-a`、`H-R9A-b`、`H-R9B-1`、`H-R9B-a`、`H-R9B-d`)
  全部来自同一份普查文件。

### 4.4 R11B 说 `H-R10B-a…g` 七个号各有第三处铸号,为什么机械只看得见四个

四个看得见的是 `a` / `b` / `f` / `g`。另外三个各有**声明式的**原因,不是随机漏:

- **`H-R10B-c` / `H-R10B-d`** 的锚点是 `data/ledger.tsv:1625` 这种形状,
  而 **`tsv` 不在校验器的扩展名白名单 `CITE_EXTS` 上**,连锚点都不算(见 §4.5);
- **`H-R10B-d`** 那一行的第二个路径 `apps/desktop/src/plugins/hello-runtime/plugin.runtime.js`
  **后面没有行号**,`RE_ANCHOR` 要求 `:数字`,所以也不成锚点;
- **`H-R10B-e`** 的第三处锚点是 `apps/desktop/playwright.config.ts:1`,基线可解析,
  **它本来就已经被算进 3 个实体里了**,不需要变体 B 才看得见。

### 4.5 `H-R11C-A-a` —— `.tsv` 不在锚点白名单上

`scripts/verify_citations.py:169 @ 25c612f`

```python
CITE_EXTS = "py|mdx|md|yaml|yml|toml|c|h|sh|json|tsx|ts|mjs|js|nix|rs|txt"
```

`data/ledger.tsv` 是本项目的中心资产(全仓 8,530 个文件的分层台账),
指向它某一行的锚点处在 CLAUDE.md 说的那个「**比 UNCHECKED 更隐蔽**」的状态:
既不校验,也不计数,连分母都进不去。

**如实报覆盖面**:全语料 `*.tsv:数字` 形状的串**只有 1 处**,就是 R10B 主线移交表那一条。
这不是一片积压,是一个**原理上的口子**。要不要补 `tsv` 由下一轮定;补的话按 R10B 立的
规矩,连同一次全语料前后对比一起补。

---

## §5 任务二逐条裁决:100 个实体全部定档,新查出 7 条隐形欠账

**结论(先写,三条):**

1. **100 个实体全部定档,无一悬空**。逐实体台账在
   `data/r11c/a-id-collisions-verdicts.tsv`,档位与判据见下表。
2. **新查出 7 条与 `H-R10B-a` 同型的隐形欠账,全部来自同一处:R8D 片底稿
   `notes/r8d-raw-provider-identity.md:2702-2708` 的 7 条移交项。** 它们用的是通用号
   `H-1`…`H-7`,而这些号在语料里都带着别的轮次写下的「结清」;R8D 主线移交表用的是
   `H-R8D-a`…`H-R8D-j`,**这 7 条一条都没进去**,报告里也**没有**其他轮那句
   「片内移交留在各片底稿」的声明。铸 `H-R11C-A-b`。
   **规模比 `H-R10B-a` 的 2 条大 3.5 倍。**
3. **另发现 R11B 名单之外的第 5 个误报**:`H-7` 的一个「铸号位」
   (`notes/r8d-raw-credentials-security.md:271`)其实是引用 CLAUDE.md 里那条 H-7 教训,
   不是铸号。判据与 §4.1 那四条同型。

### 5.1 档位与计数

```verify
python3 data/r11c/a-id-collisions-verdicts.py --counts
```

```text
NO-CLOSURE        41
NAMED             14
DECLARED          14
REVIEWED          13
HIDDEN-DEBT        7
FALSE-POSITIVE     5
SHAPE-CONFUSION    3
SELF-RULED         3
合计               100
```

| 档 | 数 | 判据 | 是否构成「随号消失」 |
|---|---|---|---|
| `NO-CLOSURE` | 41 | 剔除两份普查文件后,该号在全语料**没有任何** STRONG 处置语 | **否** —— 没有那句「结清」可供误读。(但它们仍是**未处置**的移交项,只是没被误标为已结) |
| `NAMED` | 14 | 有 STRONG 处置语点名了本实体的锚点或铸号文件 | 否,已处置 |
| `DECLARED` | 14 | 该轮主线报告**显式声明**「各片底稿另有簇内移交项……留在各自底稿的移交节,不在本表重复」 | 否 —— 在册,只是分散存放 |
| `REVIEWED` | 13 | 有真处置语未点名本实体,但该实体的锚点串**此后仍被别的文件提及** | 否(逐条读过,见 §5.4) |
| `HIDDEN-DEBT` | **7** | 有真处置语、未点名本实体、锚点此后无人再提、**且所属轮次无「片内移交留在底稿」声明** | **是** —— 本片的主要发现,见 §5.2 |
| `FALSE-POSITIVE` | 5 | 该「铸号位」实为交叉引用(§4.1 + §5.3) | 否,不是铸号 |
| `SHAPE-CONFUSION` | 3 | 铸号文本里的案号带 ▲/■/◇/◎ 前缀,是**片内定案号**不是移交号 | 否,§5.5 |
| `SELF-RULED` | 3 | 处置语就落在该实体自己的铸号行 | 否,该行自带处置 |

**`DECLARED` 这一档的判据是可查的一句话**,不是我的印象:

`reports/round-9a-capability-organization.md:334`

> *(各簇底稿另有 60 余条簇内移交项,均带锚点,留在各自底稿的移交节,不在本表重复。)*

R9A / R9B / R10 / R10B 四轮都有这句(位置见 `DECLARED_ROUNDS`),**R8D 没有**。

### 5.2 `H-R11C-A-b` —— R8D 片底稿的 7 条移交项从未进入任何账

R8D 有两张移交表,用的是**两套号**:

`reports/round-8d-cli-completion.md:424`

```
| **H-R8D-a** | R8E(建议新开) | `assign_layers.py` 里 round=`UNCLAIMED` 的 171 个文件;清单见 `notes/r8d-02-coverage-audit.md` §5–§6 | 171 个 L1 文件 / 104,656 行从未被任何一轮认领,含 R6 计划点名的 skills 全链与学习闭环全部 |
```

而片底稿自己那张表用的是 `H-1`…`H-7`:

`notes/r8d-raw-provider-identity.md:2702`

```
| H-1 | `hermes_cli/models.py:1282` vs `hermes_cli/auth.py:2003` | `aliyun` / `build-nvidia` / `deep-seek` / `nemotron` / `nim` / `vertexai` 六个别名在 `hermes model` 侧可解,`--provider <它>` 抛 `Unknown provider` | 已逐个实测(见 ■-2);修法是把这 6 个补进对应插件的 `aliases` |
```

**主线那 10 条 `H-R8D-a…j` 与片底稿这 7 条内容上无一重合**(前者是台账 UNCLAIMED、
kanban_db 行数、env_loader 锁、iron_proxy、models.py 裸 urlopen、managed_scope、
chapters 排版、docstring ▲、R12 前置、pyproject extra;后者全是 provider 身份映射)。

**负结论的搜索面(逐条给)**:把这 7 行里的每个完整锚点串(逐字,含行号)
在快照语料(`reports/` + `notes/` + `chapters/` 全部 `.md`,276 份)里搜,
**排除面只有铸号文件自身**:

```verify
python3 data/r11c/a-id-collisions-orphans.py --cid H-1 2>&1 | grep -A2 "H-1 3/4"
```

```text
   0  H-1 3/4  铸=notes/r8d-raw-provider-identity.md
      锚点串=hermes_cli/auth.py:2003 hermes_cli/models.py:1282
   2  H-1 4/4  铸=notes/r9a-raw-research-pipeline.md
```

7 条逐条如下(锚点为本仓库现行行号;基线锚点带 `@ 863e313`):

| 片内号 | 铸号位 | 基线锚点 | 一句话现象 | 同号的「结清」写在哪 | 本片定档 |
|---|---|---|---|---|---|
| `H-1` | `notes/r8d-raw-provider-identity.md:2702` | `hermes_cli/models.py:1282`:`_PROVIDER_ALIASES = {` 与 `hermes_cli/auth.py:2003`:`_PROVIDER_ALIASES = {` | 六个 provider 别名在 `auth.py` 的 `_PROVIDER_ALIASES` 里没有对应项 | `notes/r8b-90-handover-rulings.md:12`(结清的是 R8A 的 `cli.py:441`) | **HIDDEN-DEBT** |
| `H-2` | `notes/r8d-raw-provider-identity.md:2703` | `hermes_cli/models.py:1335`:`"qwen": "alibaba",` | 字符串 `qwen` 在 picker 侧 = DashScope、运行时侧 = Qwen CLI OAuth | `notes/r8b-90-handover-rulings.md:13`(结清的是 R8A 的 `cli.py:599`) | **HIDDEN-DEBT** |
| `H-3` | `notes/r8d-raw-provider-identity.md:2704` | `hermes_cli/provider_catalog.py:127`:`overlay = HERMES_OVERLAYS.get(slug)` | `HERMES_OVERLAYS.get(slug)` 用 CLI slug 查 models.dev slug 键,9/43 落空 | `notes/r8c-90-rulings.md:15`(结清的是 R8A 的 `approve_pairing`) | **HIDDEN-DEBT** |
| `H-4` | `notes/r8d-raw-provider-identity.md:2705` | `hermes_cli/providers.py:402`:`"vllm": "local",` | `vllm`/`llamacpp`/`llama.cpp`/`llama-cpp` 映到 `local`,而 `get_provider('local')` 返回 `None` | 该号全语料无 STRONG 处置语 | **HIDDEN-DEBT**(无假结清,但同样从未入账) |
| `H-5` | `notes/r8d-raw-provider-identity.md:2706` | `hermes_cli/model_normalize.py:493`:`provider = _normalize_provider_alias(target_provider)` | 传入 models.dev 空间的 provider 名时所有分支落空、模型名原样返回 | `notes/r9a-raw-research-pipeline.md:2302`(定的是 R9A 自己那条 `web_research.yaml`) | **HIDDEN-DEBT** |
| `H-6` | `notes/r8d-raw-provider-identity.md:2707` | `hermes_cli/providers.py:614`:`def host_mandated_api_mode(base_url: str = "") -> Optional[str]:` | 两张 host→api_mode 表互为补集 | 该号全语料无 STRONG 处置语 | **HIDDEN-DEBT**(同 `H-4`) |
| `H-7` | `notes/r8d-raw-provider-identity.md:2708` | `hermes_cli/model_normalize.py:61`:`"trinity": "arcee-ai",` | `_VENDOR_PREFIXES` 重复键 `"trinity"` | `notes/r8b-90-handover-rulings.md:14`(改判的是 R8A 的 `require_readable_config_before_write`) | **HIDDEN-DEBT** |

**为什么这 7 条比 `H-R10B-a` 更值得警惕**:`H-R10B-a` 的三处铸号至少**号族相同**
(`H-R10B-*`),一个想查它的人会查到三处;这 7 条挂的是 `H-1`…`H-7`,
**任何按号查的动作(包括 R11B 的移交普查、R12 的装订)都会先撞上 R8A/R8B 那一套的结清**。

**本片不裁决它们的技术内容**(那是 provider 身份映射,属 R8D 簇,不在本片射程),
只裁决它们的**账面状态**:**从未入账,现予立案 `H-R11C-A-b`,列入移交。**

### 5.3 第 5 个误报:`H-7` 的一处「铸号位」是引用不是铸号

`notes/r8d-raw-credentials-security.md:271`

> **(c) 写 config 前先做可读性守卫。** 这正是 CLAUDE.md 里 R8B "H-7 负结论"教训点名的那道闸:

这一行是**援引** CLAUDE.md 里那条 H-7 教训来解释另一段代码,不是给 `H-7` 铸第二次号。
与 §4.1 那四条同判据、同结论。**R11B 的误报名单应为 5 个,不是 4 个**
—— 但**撞号的号数不变**(`H-7` 仍因 R8A / R8D-provider-identity / R9A 三处而撞),
变的是实体数。

### 5.4 `REVIEWED` 13 个逐条为什么不判欠账

判据是**锚点串此后仍被别的文件提及**,即「后一轮不写案号、直接按锚点接着做」这一种。
逐条:

| 实体 | 锚点 | 此后提及处(命中数) | 结论 |
|---|---|---|---|
| `H-1` 2/4 | `cli.py:441` | 6 | R8B 的 `notes/r8b-02-h1-h2-config-debt.md` 整篇就是结算它,**已处置** |
| `H-1` 4/4 | `batch_runner.py:1237` | 2 | R9A 片内已定案(`chapters/r9a-*` 亦述),**已处置** |
| `H-2` 2/4 | `cli.py:599` | 3 | 同 `H-1` 2/4,R8B 结算,**已处置** |
| `H-5` 1/3 | `ui-tui/src/gatewayTypes.ts:89` | 1 | R10 客户端轮次读过该文件,**已被后轮覆盖** |
| `H-R8D-e` 2/2 | `hermes_cli/models.py:4612` | 4 | R9A 的 `notes/r9a-h-r8d-ef-surveys.md` 专章普查并「关闭并加重」,**已处置** |
| `H-R9A-b` 3/3 | `gateway/kanban_watchers.py` | n/a(铸号行无带行号锚点) | R9D 片内条目,归 `DECLARED` 同源 |
| `H-R9B-a` 2/4、`H-R9B-b` 2/3、`H-R9B-c` 2/3 | video 片各自的 a/b/c | n/a | R9B video 片内号,R9B 报告已声明片内移交留底稿 |
| `H-R9B-a` 3/4、`H-R9B-b` 3/3、`H-R9B-c` 3/3 | R9B 主线 a/b/c | 7 / 3 / 1 | 主线正式号,R9C 已接手(`reports/round-9c-*`) |
| `H-R9B-a` 4/4 | `tools/transcription_tools.py` | n/a | R9C 报告里的续转行,非独立铸号 |

**共同点**:这 13 个都能在语料里找到「后来有人碰过这块」的痕迹,
所以「随号消失」的第三个条件(此后无人再提)不成立。
**这一档的判据比 HIDDEN-DEBT 弱**,如实标注:它证明的是「不是彻底失联」,
不是「已经有人给了结论」。

### 5.5 `SHAPE-CONFUSION` 3 个:片内定案号被当成了移交号

三个都在 `notes/r10b-raw-capability-panels.md`,案号形如 `▲-H-1` / `◎-H-1` /
`▲-H-2` / `■-H-2` / `■-H-3` —— **「H」是片号(片 H),不是「Handover」**。
R11B 只点名了 `■-H-3` 一处并称之为「一个已知的形状混淆」;**实际是 3 个实体**。

`notes/r10b-raw-capability-panels.md:1045`

> ### ▲-H-2 —— `src/plugins/README.md` 说「目前没有内置插件」,实际有三个

这一条与 R11B 定的案号纪律(片内铸号必须带片标识)是同一件事的两面:
**片内定案号用了 `-H-N`,而移交号用了 `H-N`,两者在纯文本里无法区分。**
建议 R12 装订时把片内定案号统一写成 `▲-R10B-H-2` 形式。

---

## §6 本片产出的记号与案号汇总

| 记号 | 内容 | 锚点 + 摘录 |
|---|---|---|
| **■-R11C-A-01**(中高) | pet 的 profile 作用域在服务端与客户端各缺一半;同一个「领养」有两条路径落在两个 profile | `tui_gateway/methods_session.py:1800`:`@method("pet.generate")` 与 `apps/desktop/src/store/pet-gallery.ts:63`:`const petRpc = <T>(request: GatewayRequest, method: string, params: Record<string, unknown> = {}): Promise<T> =>` |
| **■-R11C-A-02**(中) | `gateway-pill` 是唯一未声明 `defaultEnabled` 的内置插件,默认开启且在状态栏可见性菜单里关不掉 | `apps/desktop/src/plugins/gateway-pill/plugin.tsx:350`:`const plugin: HermesPlugin = {` |
| **▲**(地图级) | `website/docs` 说「核心树里今天没有桌面插件」,实有三个自动注册 | `website/docs/developer-guide/desktop-plugin-sdk.md:62` 的 `differences. No desktop plugins ship in the core tree today — reference demos` |
| **▲(码内)** | `contrib/plugins.ts` 的模块 docstring 上两行说「drop a folder in 就自动注册」,下一行说「树里一个都没有」 | `apps/desktop/src/contrib/plugins.ts:4`:`*    \`HermesPlugin\` registers automatically (vite glob — drop a folder in).` |

**跨轮 ▲ 计数口径提醒**:地图级 ▲ **1** 条、▲(码内)**1** 条,两行分开报(CLAUDE.md R11B 定)。
R10B 的 `▲-H-2` 是**同一条断言的第三处出处**,本片只补出处,**不重复计数**。

## 移交

| 移交项 | 去向 | 锚点 + 摘录 | 一句话现象 |
|---|---|---|---|
| **H-R11C-A-a** | R12 前置(制度) | `scripts/verify_citations.py:169 @ 25c612f`:`CITE_EXTS = "py\|mdx\|md\|yaml\|yml\|toml\|c\|h\|sh\|json\|tsx\|ts\|mjs\|js\|nix\|rs\|txt"` | `tsv` 不在锚点白名单,指向 `data/ledger.tsv` 某行的锚点既不校验也不计数(全语料实测 **1 处**,在 R10B 主线移交表);要不要补由下一轮定,补则连同全语料前后对比一起补 |
| **H-R11C-A-b** | **R12 前置(必须处理)** | `notes/r8d-raw-provider-identity.md:2702` 的 `hermes_cli/models.py:1282`:`_PROVIDER_ALIASES = {` | R8D 片底稿的 7 条移交项(`H-1`…`H-7`,provider 身份映射)**从未进入任何账**:R8D 主线移交表用 `H-R8D-a…j` 且内容无一重合,报告也没有其他轮那句「片内移交留在各片底稿」的声明;而 `H-1`…`H-7` 在语料里都带着别轮写的「结清」。7 条锚点串在铸号文件之外**命中 0**(§5.2) |
| **H-R11C-A-c** | R12 装订 | `notes/r10b-raw-capability-panels.md:1045` 的 `### ▲-H-2 —— ` | 片内定案号写成 `▲-H-2` / `■-H-3`,与移交号 `H-2` / `H-3` 在纯文本里无法区分,已污染撞号普查 3 个实体;建议统一为 `▲-R10B-H-2` 形式 |
| **H-R11C-A-d** | R12 前置(方法论) | `data/r11c/a-id-collisions-coverage.py:57`:`CENSUS_FILES = frozenset({` | 「某案子被处置过没有」这类测量会被**上一轮的普查清单**污染:`H-R10B-a` 两个实体在不剔除读数下被判 COVERED,而点名它们的正是 R11B 那份「它们没被处置」的清单。R12 若再做同类普查,必须报剔除与不剔除两个读数 |

**对上一轮读数的两处更正**(不新立案号,写在这里供 R12 引用):

1. R11B 的误报名单应为 **5 个**(增 `H-7` 的 `notes/r8d-raw-credentials-security.md:271` 那一处),不是 4 个;**撞号号数不变**。
2. R11B 给漏报 `H-R9B-6` 的原因(「锚点写在标题下一行之外被滤掉」)**不成立**;真机制是搜索窗过宽导致锚点集假相交、两个实体被假合并(§4.2)。方向相反,对下一轮改判据有实际影响。

## §7 交付自检

**引用关卡与证据关卡(本片文件,退出码均为 0)**:

```text
$ python3 scripts/verify_citations.py /home/user/hermes-agent notes/r11c-raw-id-collisions.md
citations=46  OK=34  UNCHECKED=12
可校验比例 OK/46 = 73.9%          (≥ 70% 下限)
table_anchors=38  OK=17  UNCHECKED=21
MISMATCH=0  BLOCK-DRIFT=0  TABLE-DRIFT=0  TABLE-OUT-OF-RANGE=0
OK: every code-block-backed citation matches the baseline

$ python3 scripts/verify_evidence_commands.py notes/r11c-raw-id-collisions.md
verify-blocks paired=8  unpaired=0  differing=0  timedout=0
runnability   ran=0  runfail=0  skipped-mutating=0
OK: every paired ```verify command reproduces its pasted output
```

**表格锚点声明率单独报(CLAUDE.md R11B 定,不并入可校验比例)**:
`table_anchors=38  OK=17`,声明率 44.7%。未声明摘录的 21 处仍是 TABLE-UNCHECKED。
**移交表 4 条锚点全部按声明式写法**(锚点后紧跟反引号摘录)。

**基线只读自查**:`git -C /home/user/hermes-agent status --porcelain` 输出为空,
HEAD = `863e31318`。本片全程只读基线,未执行任何基线代码,
故「惰性安装纪律」无实际触发点(未跑过 `python -c "import hermes..."` 之类)。

**语料快照**:`8d6bac6`(R11C 批次二派发那一条 commit)。片 C / D / E / F 并发改历史
`notes/`,从工作区读会让读数漂移;本片所有探针读快照,**读数可重跑**。
唯一从工作区解析的是**引用关卡**(它按工作区解析锚点),所以本底稿里
`notes/r10b-raw-capability-panels.md:1045` / `:1365` 这两处锚点在交付时刻已随片 C/D
的改动漂过一次并已改正;**若主线合并时再漂,`--fix` 可无歧义修正**。

## 完成信号

**片 A 完成。** 产出文件:

| 文件 | 内容 |
|---|---|
| `notes/r11c-raw-id-collisions.md` | 本底稿(§1 结清 H-R11B-A-c、§2 结清 H-R11B-A-d、§3 方法与两个读数、§4 复核 39/35/漏报、§5 100 个实体逐条定档、§6 记号与移交) |
| `data/r11c/a-id-collisions-audit.py` | 铸号位 × 处置位审计(批次一遗留,本次复核后把语料快照从 `4b215e8` 上调到 `8d6bac6`) |
| `data/r11c/a-id-collisions-coverage.py` | 新增:每个(案号, 实体)的处置覆盖标签 + `--no-census` 第二读数 |
| `data/r11c/a-id-collisions-coverage.tsv` | 上者的明细 TSV |
| `data/r11c/a-id-collisions-orphans.py` | 新增:实体锚点串在铸号文件之外的命中数(负结论机械化) |
| `data/r11c/a-id-collisions-underreport.py` | 新增:复核 R11B 自陈的漏报与实体数偏低,两个变体读数 |
| `data/r11c/a-id-collisions-verdicts.py` / `.tsv` | 新增:100 个撞号实体的逐条定档台账 |

| `data/r11c/a-id-collisions-audit.tsv` / `-followup.tsv` | 上表第一个脚本的两种明细(批次一留下的旧版**已按新语料快照 `8d6bac6` 整份重生成**,不再是无底稿的中间产物) |

批次一留下的 `-audit.py` 本片**逐行读过并复核**:铸号判据是 `import` R11B 探针得到的
(所以 39 / 100 与上一轮严格可比),处置语判据只发现、不判开闭(符合 CLAUDE.md R11C 那条)。
唯一改动是把语料快照从 `4b215e8` 上调到 `8d6bac6`,理由见 §3.2。

两条关卡命令均**退出码 0**,读数见 §7。
