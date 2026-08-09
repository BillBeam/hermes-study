# r10b 片 I · `apps/desktop` 的 i18n 语言包与国际化装配 —— 底稿(L3 知悉用途)

> 层:**L3**(知悉用途)。判据用 `data/r10b/l3-criteria.md` 的 L3-1 ~ L3-5,**不适用** L2 五条。
> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。路径一律从 hermes-agent 仓库根写起。
> 本片是本项目十轮以来**第一个 L3 片**,故 §10 成本自报按派工书要求从详。

---

## 0. 本片范围与逐文件点名(L3-1)

13 个文件 / 17,378 行,全部在 `apps/desktop/src/i18n/` 下。核对:

```verify
# 片 I 的文件数与行数(以派工清单为准,不手数)
cd /home/user/hermes-agent
n=0; tot=0
while read -r p; do l=$(wc -l < "$p"); tot=$((tot+l)); n=$((n+1)); done \
  < <(sed 's#^#/home/user/hermes-agent/#' /home/user/hermes-study/data/r10b/slices/I.txt)
echo "files=$n lines=$tot"      # => files=13 lines=17378
```

**注意目录里还有 4 个 `*.test.*` 文件**(`languages.test.ts` 48 / `runtime.test.ts` 75 /
`plugin-i18n.test.tsx` 126 / `context.test.tsx` 250,合计 499 行),它们属 **LT 层**,
不在本片 13 个文件内,但本片把它们当**行为规格**读并运行(见 §7)。
`wc -l` 目录通配得到 17,877 行 = 17,378 + 499,两个数不要混。

### 装配件(7 文件 / 567 行)——「知悉用途」的重量全在这里

| 全路径 | 它是什么、谁读它 |
|---|---|
| `apps/desktop/src/i18n/catalog.ts`(14 行) | **五个语言包的总装表**。`apps/desktop/src/i18n/catalog.ts:8`:`export const TRANSLATIONS: Record<Locale, Translations> = {` 把 5 个包装成 `Record<Locale, Translations>`。被 `context.tsx` 与 `runtime.ts` 读;是整簇唯一一处**编译器强制「每个 Locale 都得有包」**的地方 |
| `apps/desktop/src/i18n/index.ts`(31 行) | **对外唯一门面**,纯 re-export,无逻辑。`apps/desktop/src/i18n/index.ts:1`:`export { TRANSLATIONS } from './catalog'`。全 app 与插件 SDK 都从 `@/i18n` 进来,不直接 import 内部模块 |
| `apps/desktop/src/i18n/types.ts`(2,537 行) | **类型契约**,手写、非生成。`apps/desktop/src/i18n/types.ts:8`:`export type Locale = 'en' \| 'zh' \| 'zh-hant' \| 'ja' \| 'ar'` 定义 5 个 locale id;`interface Translations` 定义全部可翻译字符串面。被 5 个语言包 + `define-locale.ts` + `catalog.ts` 读 |
| `apps/desktop/src/i18n/define-locale.ts`(41 行) | **部分语言包的兜底合并器**。`apps/desktop/src/i18n/define-locale.ts:39` 的 `defineLocale` 把「只写了一部分」的覆盖对象深合并到 `en` 上,产出一个结构完整的 `Translations`。被 `ja.ts` / `zh-hant.ts` / `ar.ts` 读 |
| `apps/desktop/src/i18n/languages.ts`(103 行) | **locale 元数据 + 输入归一化**。`apps/desktop/src/i18n/languages.ts:7`:`export const LOCALE_OPTIONS = [` 是语言选择器的数据源;`LOCALE_ALIASES` 把 `zh-CN` / `zh_TW` / `arabic` / `العربية` 等 33 个写法归一到 5 个 id。被 `context.tsx`、`runtime.ts`、语言选择器读 |
| `apps/desktop/src/i18n/runtime.ts`(66 行) | **非 React 的模块级翻译器**。`apps/desktop/src/i18n/runtime.ts:64` 的 `translateNow` 供 store / handler 这类拿不到 React context 的地方用;它导出的 `translateFrom` 是**核心与插件共用的那一条 active→en→key 回落逻辑** |
| `apps/desktop/src/i18n/plugin-i18n.ts`(116 行) | **插件私有语言包注册表**。`apps/desktop/src/i18n/plugin-i18n.ts:48`:`const registry = new Map<string, Map<Locale, PluginMessages>>()`,按 pluginId 分桶。被插件 SDK(`apps/desktop/src/sdk/index.ts`)与插件加载器读 |
| `apps/desktop/src/i18n/context.tsx`(196 行) | **React 侧的装配中心**。`apps/desktop/src/i18n/context.tsx:95` 的 `I18nProvider` 持有当前 locale、读写 hermes 配置 `display.language`、设置 `<html lang/dir>`、把 `t` 灌进 context。被 `apps/desktop/src/main.tsx:53` 挂在全 app 根上 |

### 数据表(5 文件 / 14,274 行)——形态相同,逐个列全路径

五个包都导出一个巨型嵌套对象,叶子是字符串或插值函数(`open => \`...\``)。
**两种写法,差别是有没有兜底网**(这是本片最要紧的一条结构事实,详见 §4.1):

| 全路径 | 行数 | 写法 | 缺 key 时 |
|---|---|---|---|
| `apps/desktop/src/i18n/en.ts` | 2,984 | `apps/desktop/src/i18n/en.ts:5`:`export const en: Translations = {` | 它就是兜底源本身 |
| `apps/desktop/src/i18n/zh.ts` | 3,145 | `apps/desktop/src/i18n/zh.ts:5`:`export const zh: Translations = {` | **无 `defineLocale` 兜底**,枚举键靠 tsc 保完整,`Record` 桶内的键**无人保证** |
| `apps/desktop/src/i18n/ja.ts` | 2,824 | `apps/desktop/src/i18n/ja.ts:5`:`export const ja = defineLocale({` | 构建期合并到 `en`,结构必然完整 |
| `apps/desktop/src/i18n/zh-hant.ts` | 2,710 | `apps/desktop/src/i18n/zh-hant.ts:5`:`export const zhHant = defineLocale({` | 同上 |
| `apps/desktop/src/i18n/ar.ts` | 2,611 | `apps/desktop/src/i18n/ar.ts:3`:`export const ar = defineLocale({` | 同上;另是唯一 RTL locale |

---

## 1. 这一簇解决什么问题

一个 Electron 桌面端要把**约 2,763 条界面字符串**用 5 种语言呈现,并且:

1. **不能靠运行时抓取**——桌面端离线可用,语言包必须编译进包体;
2. **不能要求每种语言都翻译完**——否则加一句英文就阻塞 4 个语言的发布;
3. **既要给 React 组件用,也要给非 React 的 store / handler 用**——后者拿不到 context;
4. **插件要能自带翻译**,又不能污染核心的键空间;
5. **阿拉伯语要整页镜像**(RTL)。

这一簇的答案是:**一个手写类型契约当中央真值 + 两种语言包写法(完整 / 部分)+ 两个翻译器
(React 的 `t` 对象、模块级的 `translateNow`)+ 一个按插件 id 分桶的插件注册表**。

---

## 2. 形态账(L3-2)

### 2.1 按形态的文件数 / 行数

```verify
cd /home/user/hermes-agent/apps/desktop/src/i18n
wc -l en.ts zh.ts ja.ts zh-hant.ts ar.ts | tail -1   # 数据表  5 文件 14274 行
wc -l types.ts                                        # 类型契约 1 文件  2537 行
wc -l catalog.ts context.tsx define-locale.ts index.ts \
      languages.ts plugin-i18n.ts runtime.ts | tail -1 # 装配件  7 文件   567 行
```

| 形态 | 文件数 | 行数 | 占比 |
|---|---:|---:|---:|
| 数据表(语言包) | 5 | 14,274 | 82.1% |
| 类型契约 | 1 | 2,537 | 14.6% |
| 运行时装配 | 7 | 567 | **3.3%** |
| 合计 | 13 | 17,378 | 100% |

### 2.2 叶子键规模与逐语言覆盖率

派工书问的第一个问题是「5 个语言包的叶子键是否等量」。**答案不是一个数,而是要分两层看**,
因为「写在源码里的键」与「运行时实际存在的键」不是一回事(`defineLocale` 会在构建期补齐)。

计数用一次性探针 `data/r10b/probes/probe_i_leafkeys.mjs`(**用 TypeScript 官方 parser 静态解析,
不执行、不解析 import**)。它把 `en.ts` 里 `fieldLabels: FIELD_LABELS` 这种**不透明标识符**
单列,并额外解析 `apps/desktop/src/app/settings/constants.ts` 把那两棵子树接回来,
否则 `en` 与其他 4 个包**不可比**(初版就因此把 `en` 少算了 138 个叶子)。

```verify
# 需要一个装了 typescript 的 checkout 提供 NODE_PATH(R10B 的 TS 副本即可)
NODE_PATH=/home/user/r10b-ts/hermes-agent/node_modules \
  node /home/user/hermes-study/data/r10b/probes/probe_i_leafkeys.mjs /home/user/hermes-agent
```

```console
file            authoring        leaves  opaque  call-subtrees  spreads
en.ts           literal            2763       0              2        0
zh.ts           literal            2762       0              2        0
ja.ts           defineLocale()     2335       0              2        0
zh-hant.ts      defineLocale()     2335       0              2        0
ar.ts           defineLocale()     2181       0              0        0
types.ts        interface Translations   2251       0              0        0
```

逐语言对 `en` 的覆盖(shared = 与 en 同名的叶子路径数;extra = en 没有的):

```verify
BASE=/home/user/hermes-agent
TS_NM=/home/user/r10b-ts/hermes-agent/node_modules
PROBE=/home/user/hermes-study/data/r10b/probes/probe_i_leafkeys.mjs
OUT=$(mktemp -d)
for f in en zh ja zh-hant ar; do
  NODE_PATH=$TS_NM node "$PROBE" "$BASE" --paths $f.ts | sort > "$OUT/$f.paths"
done
EN=$(wc -l < "$OUT/en.paths")
printf '%-9s %7s %7s %9s %9s\n' locale leaves shared extra cover
for f in en zh ja zh-hant ar; do
  n=$(wc -l < "$OUT/$f.paths")
  both=$(comm -12 "$OUT/en.paths" "$OUT/$f.paths" | wc -l)
  extra=$(comm -13 "$OUT/en.paths" "$OUT/$f.paths" | wc -l)
  printf '%-9s %7d %7d %9d %8.1f%%\n' "$f" "$n" "$both" "$extra" "$(echo "scale=4;100*$both/$EN" | bc)"
done
comm -23 "$OUT/en.paths" "$OUT/zh.paths"   # en 有而 zh 没有的 20 个键
rm -rf "$OUT"
```

```console
locale     leaves  shared     extra     cover
en           2763    2763         0    100.0%
zh           2762    2743        19     99.3%
ja           2335    2335         0     84.5%
zh-hant      2335    2335         0     84.5%
ar           2181    2175         6     78.7%
```

**怎么读这张表(三条,缺一条就会读错):**

1. **`ja` / `zh-hant` / `ar` 的 extra=0、cover<100%,不是缺陷**。它们用 `defineLocale`,
   没写的键构建期从 `en` 补齐。cover 那一列读作**「这个语言实际翻译了多少」**:
   日文/繁中各译了 84.5%,阿拉伯语 78.7%,其余显示英文。
2. **`ja` 与 `zh-hant` 都恰好 2,335 且集合完全相同**——两者是同一批工作产出的。
3. **`zh` 的 shared=2,743 才是真问题**:它是 `zh: Translations = {...}`,**没有 `defineLocale` 兜底**。
   en 有而 zh 没有的那 20 个键,运行时就是 `undefined`(详见 §6 ■-1)。
   `zh` 的 extra=19 全是 `messaging.platformIntro.*`,那是**设计如此**(§4.4),不是多余。

### 2.3 其他规模数

```verify
cd /home/user/hermes-agent/apps/desktop
# 模块级翻译器 translateNow 的调用点(排除 i18n 自身与测试)
grep -rn "translateNow(" src --include=*.ts --include=*.tsx \
  | grep -v "^src/i18n/" | grep -v "\.test\." | wc -l     # => 129
grep -rln "translateNow(" src --include=*.ts --include=*.tsx \
  | grep -v "^src/i18n/" | grep -v "\.test\." | wc -l     # => 24  (个文件)
# locale 别名条数
grep -cE "^  [a-zA-Z_'العربية-]+: '(en|zh|zh-hant|ja|ar)'," src/i18n/languages.ts  # => 33
```

| 量 | 数 |
|---|---:|
| locale 数 | 5 |
| `LOCALE_ALIASES` 归一化条目 | 33 |
| `translateNow` 调用点 / 涉及文件 | 129 / 24 |
| `Translations` 接口里**枚举**的叶子槽位 | 2,251 |
| `en` 实际写下的叶子 | 2,763 |
| 差额(落在 `Record<...>` 开放桶里、类型**不枚举**的键) | **512** |

最后那 512 是本片最有解释力的一个数:**类型契约只管住了 2,251 个位置,另外 512 个位置
tsc 一句话都不说**。§4.2 与 §6 都建立在这个数上。

---

## 3. 一条真链(L3-3):一个中文用户打开快捷键设置,看到 4 行没翻译的原始 id

选这条链是因为它把「被谁读 → 在哪装配 → 缺了会怎样」三段都走完了,而且末端是一个**真实可见的现象**。

### 跳 1 —— 语言包在 `catalog.ts` 总装

`apps/desktop/src/i18n/catalog.ts:8 @ 863e313`

```ts
export const TRANSLATIONS: Record<Locale, Translations> = {
  en,
  zh,
  'zh-hant': zhHant,
  ja,
  ar
}
```

`Record<Locale, Translations>` 是**整簇唯一一处**强制「`Locale` 里每个 id 都必须有包」的注解。

### 跳 2 —— `ja/zh-hant/ar` 在构建期被合并到 `en` 上;`zh` 不走这条路

`apps/desktop/src/i18n/define-locale.ts:39 @ 863e313`

```ts
export function defineLocale(overrides: TranslationOverrides): Translations {
  return mergeTranslations<Translations>(en, overrides)
}
```

`zh` 则直接标注接口类型,**不经过这个函数**,所以它没有兜底网:

`apps/desktop/src/i18n/zh.ts:5 @ 863e313`

```ts
export const zh: Translations = {
```

### 跳 3 —— `I18nProvider` 把 locale 装配到三个地方

`apps/desktop/src/i18n/context.tsx:104 @ 863e313`

```tsx
  useEffect(() => {
    localeRef.current = locale
    setRuntimeI18nLocale(locale)
    applyDocumentLocale(locale)
  }, [locale])
```

一次 locale 变更同时推给:React context(`t`)、模块级翻译器(`setRuntimeI18nLocale`,给那 129 个
`translateNow` 调用点用)、以及 DOM 的 `lang`/`dir`(`applyDocumentLocale`,阿拉伯语在此翻成 RTL)。
Provider 挂在全 app 根上,**且不传 `initialLocale`**:

`apps/desktop/src/main.tsx:53 @ 863e313`

```tsx
          <I18nProvider>
```

### 跳 4 —— `t` 交给消费者,是**直接对象访问**,不是函数调用

`apps/desktop/src/i18n/context.tsx:178 @ 863e313`

```tsx
  const value = useMemo<I18nContextValue>(
    () => ({
      configLoadError,
      isLoadingConfig,
      isSavingLocale,
      locale,
      saveError,
      setLocale,
      t: TRANSLATIONS[locale]
    }),
    [configLoadError, isLoadingConfig, isSavingLocale, locale, saveError, setLocale]
  )
```

`t` 就是**那个 locale 的整棵对象树本身**。于是组件写 `t.keybinds.actions[id]`
——**一次普通的属性读取**。这一条路上**没有任何回落逻辑**(回落只存在于 `translateNow` 那条路,见 §4.3)。

### 跳 5 —— 类型契约在这个位置是开放桶,tsc 不管

`apps/desktop/src/i18n/types.ts:262 @ 863e313`

```ts
    categories: Record<string, string>
    actions: Record<string, string>
```

### 跳 6 —— `en` 有 4 个终端相关的快捷键标签

`apps/desktop/src/i18n/en.ts:263 @ 863e313`

```ts
      'view.showFiles': 'Show file browser',
      'view.showTerminal': 'Toggle terminal',
      'view.newTerminal': 'New terminal',
      'view.nextTerminal': 'Next terminal',
      'view.prevTerminal': 'Previous terminal',
      'view.closeTerminal': 'Close terminal',
```

`zh` 在**同一个位置**只到 `view.showTerminal` 就跳到别的键了:

`apps/desktop/src/i18n/zh.ts:258 @ 863e313`

```ts
      'view.showFiles': '显示文件浏览器',
      'view.showTerminal': '显示终端',
      'view.terminalSelection': '将终端选区发送到输入框',
```

### 跳 7 —— 缺了会怎样:设置页显示原始 action id

`apps/desktop/src/app/settings/keybind-settings.tsx:203 @ 863e313`

```tsx
  const label = k.actions[action.id] ?? action.label ?? action.id
```

**结论**:中文用户打开「设置 → 快捷键」,`view.newTerminal` / `view.nextTerminal` /
`view.prevTerminal` / `view.closeTerminal` 四行显示的是**原始 id 字符串**而不是中文标签。
不崩、不空白,但明显是漏译。同一文件的 `:76`、`:90`、`:263` 与下面这个 tooltip 标签
用的都是同一个 `?? id` 兜底形状,所以这四个 action 的 tooltip 也一样显示原始 id:

`apps/desktop/src/components/ui/tooltip.tsx:216 @ 863e313`

```tsx
function TipKeybindLabel({ actionId, text }: TipKeybindLabelProps) {
  const { t } = useI18n()
  const hint = useKeybindHint(actionId)

  const label = text ?? t.keybinds.actions[actionId] ?? actionId
```

**链上唯一一处没有兜底的读取**在命令面板:

`apps/desktop/src/app/command-palette/index.tsx:765 @ 863e313`

```tsx
                  id: 'nav-new-window',
                  keywords: ['window', 'instance', 'open', 'new'],
                  label: t.keybinds.actions['session.newWindow'],
                  run: () => void openNewWindow()
```

`label` 后面没有 `??`。经查该键 `apps/desktop/src/i18n/zh.ts:235` **有**中文翻译,
所以当前不触发问题——但它是这条链上最脆的一点(见 §9 移交项 H-R10B-I-b)。

---

## 4. 逐区域说明

### 4.1 两种语言包写法,以及为什么 `zh` 是特例

`apps/desktop/src/i18n/types.ts:1 @ 863e313`

```ts
// Desktop i18n type contract.
//
// `Translations` is the single source of truth for every translatable string
// surface. Fully translated locale files may satisfy this interface directly;
// partial locales should use `defineLocale()` so missing desktop-only strings
// fall back to English while new keys remain type-checked.
```

这段注释把制度说清楚了:**译全了的包可以直接标注 `: Translations`;没译全的用 `defineLocale()`**。
`en` 与 `zh` 走前者,`ja` / `zh-hant` / `ar` 走后者。

派工书问「`types.ts` 2,537 行是不是从某个语言包生成的类型?谁保证它与语言包同步?」——
**答:不是生成的,是手写的中央契约,反过来管着语言包。同步靠 tsc,但只管得住 2,251 个枚举槽位,
另外 512 个落在 `Record<...>` 开放桶里的键完全不受管**(§2.3)。所以:

- `zh` 少一个**枚举**键 → tsc 报错,进不了 main;
- `zh` 少一个**开放桶**里的键 → 没有任何东西会说话,一路到用户界面(这就是 §3 那条链)。

### 4.2 添加一个新 locale 要动哪些地方(L3 的核心问题)

派工书问「`languages.ts` 列出的语言集合与实际存在的语言包文件是否严格相等」。**严格相等,4 个来源全一致:**

```verify
cd /home/user/hermes-agent/apps/desktop/src/i18n
sed -n '8p' types.ts | grep -o "'[a-z-]*'" | tr -d "'" | sort | tr '\n' ' '; echo   # Locale 联合类型
grep -oE "^    id: '[a-z-]+'" languages.ts | sed "s/.*'\(.*\)'/\1/" | sort | tr '\n' ' '; echo  # LOCALE_OPTIONS
ls *.ts | grep -vE 'catalog|context|define-locale|index|languages|plugin-i18n|runtime|types|test' \
  | sed 's/\.ts$//' | sort | tr '\n' ' '; echo                                      # 磁盘上的包文件
# 三行输出均为:ar en ja zh zh-hant
```

`apps/desktop/src/i18n/catalog.ts:8` 的 `Record<Locale, Translations>` 是第 4 个来源,同样是这 5 个。
**但「当前相等」与「改动时会不会失衡」是两件事**——6 个必改点里只有 1 个受编译器保护:

| # | 要动的地方 | 编译器强制? |
|---|---|---|
| 1 | `apps/desktop/src/i18n/types.ts:8` 的 `export type Locale = 'en' \| 'zh' \| 'zh-hant' \| 'ja' \| 'ar'` 加 id | — 起点 |
| 2 | 新增 `apps/desktop/src/i18n/<id>.ts` 语言包 | — |
| 3 | `apps/desktop/src/i18n/catalog.ts:8` 的 `export const TRANSLATIONS: Record<Locale, Translations> = {` | **是**,漏了直接编译失败 |
| 4 | `apps/desktop/src/i18n/languages.ts:7` 的 `export const LOCALE_OPTIONS = [` | **否**(见下) |
| 5 | `apps/desktop/src/i18n/languages.ts:48` 的 `const LOCALE_ALIASES: Record<string, Locale> = {` | **否**,`Record<string, …>` 键是开放的 |
| 6 | `apps/desktop/src/i18n/context.tsx:58` 的 `const RTL_LOCALES = new Set<Locale>(['ar'])` | **否**,RTL 名单与其他 locale 元数据**不在同一个文件** |

第 4 点为什么不受保护——`LOCALE_OPTIONS` 用 `satisfies` 只约束了**元素形状**,数组**完整性**无人检查,
而由它派生的 `LOCALE_META` 是一次 `as` 断言:

`apps/desktop/src/i18n/languages.ts:44 @ 863e313`

```ts
export const LOCALE_META: Record<Locale, { name: string; englishName: string }> = Object.fromEntries(
  LOCALE_OPTIONS.map(locale => [locale.id, { name: locale.name, englishName: locale.englishName }])
) as Record<Locale, { name: string; englishName: string }>
```

`Object.fromEntries` 返回 `{[k: string]: T}`,靠 `as` 强断言成 `Record<Locale, …>`。
少一个 locale,**类型上仍然「完整」,运行时是 `undefined`**。

### 4.3 缺 key 的运行时回落:两条路,行为不同

派工书问「缺 key 时运行时怎么回落,回落是静默还是可见?」**两条路必须分开答:**

**路 A(`translateNow` / 插件 `t`,字符串点路径)——有三级回落:**

`apps/desktop/src/i18n/runtime.ts:31 @ 863e313`

```ts
export function translateFrom(
  source: (locale: Locale) => unknown,
  locale: Locale,
  key: string,
  args: unknown[]
): string {
  const active = render(resolvePath(source(locale), key), args)

  if (active !== null) {
    return active
  }

  if (locale !== DEFAULT_LOCALE) {
    const fallback = render(resolvePath(source(DEFAULT_LOCALE), key), args)

    if (fallback !== null) {
      return fallback
    }
  }

  return key
}
```

当前 locale → `en` → **原样返回 key**。最后一级被测试钉死:

`apps/desktop/src/i18n/runtime.test.ts:71 @ 863e313`

```ts
    setRuntimeI18nLocale('zh')

    expect(translateNow('missing.path')).toBe('missing.path')
  })
```

**路 B(React 的 `t.a.b.c`,直接属性访问)——语言层面没有回落**,靠 tsc 保证键存在;
落在 `Record` 开放桶里时,tsc 保不住,结果是 `undefined`,是否可见取决于**调用点自己写没写 `??`**。

**回落是静默还是可见?——对运维完全静默,对用户可见。** 搜索面:

```verify
cd /home/user/hermes-agent/apps/desktop/src/i18n
grep -nE "console\.|warn|error\(|logger|track|report|Sentry|telemetry|process\.env\.NODE_ENV|import\.meta\.env" \
  catalog.ts context.tsx define-locale.ts index.ts languages.ts plugin-i18n.ts runtime.ts types.ts
```

在**全部 8 个非数据文件**中搜 `console.*` / `warn` / `error(` / `logger` / `track` / `report` /
`Sentry` / `telemetry` / `NODE_ENV` / `import.meta.env`,**唯二命中都不是日志**:
`apps/desktop/src/i18n/plugin-i18n.ts:94,96,98` 的 `track` 是插件 disposer 的形参名,`apps/desktop/src/i18n/types.ts:2451` 的 `warningLine` 是一个翻译键。
**结论:回落路径上零日志、零计数、零 dev 警告**——漏译不会在任何遥测里出现,只会以英文原文
或原始 key 的形式出现在用户屏幕上。这也解释了 §6 那两条为什么能长期存在。

### 4.4 `platformIntro`:看着像漏译,其实是覆盖表(一条被证伪的怀疑)

`en` 的 `platformIntro` 是个空对象:

`apps/desktop/src/i18n/en.ts:1487 @ 863e313`

```ts
      }
    },
    platformIntro: {}
  },
```

`apps/desktop/src/i18n/ja.ts:1392`、`apps/desktop/src/i18n/zh-hant.ts:1341`、
`apps/desktop/src/i18n/ar.ts:1287` 同样是 `platformIntro: {}`,只有
`apps/desktop/src/i18n/zh.ts:1658` 填了 19 个平台。初看像「只有中文译了」,实则相反——英文原文根本不在 i18n 里:

`apps/desktop/src/app/messaging/index.tsx:821 @ 863e313`

```tsx
  m.platformIntro[platform.id] || PLATFORM_INTRO[platform.id] || platform.description
```

`PLATFORM_INTRO`(`apps/desktop/src/app/messaging/index.tsx:783`)是英文基线,i18n 里的
`platformIntro` 只是**逐平台覆盖表**。所以 `{}` 是正常状态,`zh` 的 19 条 extra 是**多译的**,不是多余的。
**这条记在这里是因为它是本片唯一一个「数字看着像缺陷、查了代码发现是设计」的地方**,
只看 §2.2 的 extra 列会判错。

### 4.5 `settings.fieldLabels` / `fieldDescriptions`:契约是**扁平**表,三种写法都合法

契约侧是**一层扁平**、键是点分字符串:

`apps/desktop/src/i18n/types.ts:422 @ 863e313`

```ts
    fieldLabels: Record<string, string>
    fieldDescriptions: Record<string, string>
```

读取侧做的也是单层查表,还顺带把 `show_reasoning` 这种 snake_case schema 键转成 `showReasoning`:

`apps/desktop/src/app/settings/field-copy.ts:13 @ 863e313`

```ts
export function schemaKeyToFieldCopyKey(schemaKey: string): string {
  return schemaKey.split('.').map(schemaSegmentToFieldCopySegment).join('.')
}

export function fieldCopyForSchemaKey(copy: Record<string, string>, schemaKey: string): string | undefined {
  return copy[schemaKeyToFieldCopyKey(schemaKey)] ?? copy[schemaKey]
}
```

三种写法:

**(1) `en` 引用片外常量。**

`apps/desktop/src/i18n/en.ts:520 @ 863e313`

```ts
      }
    },
    fieldLabels: FIELD_LABELS,
    fieldDescriptions: FIELD_DESCRIPTIONS,
```

两个常量定义在**片外**的 `apps/desktop/src/app/settings/constants.ts:388`(与 `:556`),同样过 `defineFieldCopy`:

`apps/desktop/src/app/settings/constants.ts:388 @ 863e313`

```ts
export const FIELD_LABELS: Record<string, string> = defineFieldCopy({
  model: 'Default Model',
  modelContextLength: 'Context Window',
```

**(2) `zh` / `ja` / `zh-hant` 就地写嵌套树,由 `defineFieldCopy` 压平。**

`apps/desktop/src/i18n/zh.ts:512 @ 863e313`

```ts
    fieldLabels: defineFieldCopy({
      model: '默认模型',
      modelContextLength: '上下文窗口',
      fallbackProviders: '备用模型',
      toolsets: '启用的工具集',
      timezone: '时区',
```

对应位置另见 `apps/desktop/src/i18n/zh.ts:674` / `apps/desktop/src/i18n/ja.ts:400,562` /
`apps/desktop/src/i18n/zh-hant.ts:388,550`。

**(3) `ar` 直接手写扁平点分键,不套 `defineFieldCopy`。**

`apps/desktop/src/i18n/ar.ts:465 @ 863e313`

```ts
    fieldLabels: {
      model: 'النموذج الافتراضي',
      modelContextLength: 'نافذة السياق',
      fallbackProviders: 'النماذج الاحتياطية',
      toolsets: 'مجموعات الأدوات المفعلة',
      timezone: 'المنطقة الزمنية',
      'display.personality': 'أسلوب المساعد',
```

(`fieldDescriptions` 同形,见 `apps/desktop/src/i18n/ar.ts:553`。)

三种都产出合法的扁平表,**`ar` 的写法没有 bug**(我一度怀疑它是嵌套的,查证后否定)。
唯一实际差别:`defineFieldCopy` 在 `apps/desktop/src/app/settings/field-copy.ts:38` 会抛
`Duplicate field copy key`,`ar` 的裸字面量拿不到这个运行时重复键检查。属**一致性瑕疵**,不构成缺陷。

**「动它要动哪些」**:新增一个设置项要同时改 `apps/desktop/src/app/settings/constants.ts`(英文)
与 4 个语言包里的 `defineFieldCopy` 块——**5 个文件,其中 1 个在 `src/i18n/` 之外**。

### 4.6 插件 i18n:按 pluginId 分桶,核心键空间不可达

派工书问「插件注入的键会不会覆盖内建键?有没有命名空间隔离?」**答:不会覆盖,隔离是结构性的。**

注册表按 pluginId 分桶:

`apps/desktop/src/i18n/plugin-i18n.ts:48 @ 863e313`

```ts
const registry = new Map<string, Map<Locale, PluginMessages>>()
```

而查表函数**只看自己那一桶**:

`apps/desktop/src/i18n/plugin-i18n.ts:90 @ 863e313`

```ts
export function translatePlugin(pluginId: string, locale: Locale, key: string, args: unknown[]): string {
  return translateFrom(l => registry.get(pluginId)?.get(l), locale, key, args)
}
```

`source` 闭包传的是 `registry.get(pluginId)`,**核心的 `TRANSLATIONS` 根本不在可达范围内**。
反向也成立:插件的键对核心不可见。所以:

- 插件**无法**覆盖内建键(想覆盖也够不着);
- 插件的回落链是「当前 locale → **自己的** `en` 包 → 原始 key」——注意第二级落到的是
  **插件自己的英文包**,不是 app 的英文包,因为 `translateFrom` 的 `source` 已被锁在这一桶里;
- `plugin-i18n.test.tsx` 的 `scopes bundles per plugin — no cross-read` 把这条钉死了。

**一处要知道的锐边**:`registerPluginLocales` 返回的 disposer 是

`apps/desktop/src/i18n/plugin-i18n.ts:84 @ 863e313`

```ts
  return () => {
    registry.delete(pluginId)
    $version.set($version.get() + 1)
  }
```

它删的是**整个 pluginId 桶**,不是本次注册的那批 bundle。插件调用两次 `register` 再 dispose 其中一个,
两批都没了。这不是缺陷——接口的 JSDoc 把「调一次」写成了契约:

`apps/desktop/src/i18n/plugin-i18n.ts:39 @ 863e313`

```ts
export interface PluginI18n {
  /** Merge locale bundles for this plugin (call once at `register`). Returns a
   *  disposer that drops the plugin's bundles on unload/reload. */
  register: (bundles: PluginLocaleBundles) => () => void
  /** Module-level translator against the app's active locale (mirrors
   *  `translateNow`). Non-reactive — in React prefer `usePluginI18n`. */
  t: PluginTranslate
}
```


且 `plugin-i18n.test.tsx` 的 `merges repeated registrations and drops everything on dispose`
**正是把这个行为当契约钉住的**——"drops everything" 是写在用例名里的。

---

## 5. 文档与代码的出入

### ▲-1 `DESIGN.md` 的 i18n 节把 5 个 locale 说成 4 个

`apps/desktop/DESIGN.md:287 @ 863e313`(归 `apps/desktop/DESIGN.md:283` 的 `## i18n` 标题管)

> - **Update all locales together** — `en`, `ja`, `zh`, `zh-hant`. A string change
>   in `en.ts` that skips the others is a regression (drifted punctuation,
>   stale labels). Keep trailing-punctuation and tone consistent across all four.

**整句判定**(按项目规矩连整段一起判):这句话讲了三件事——(a) 所有 locale 要一起更新;
(b) 名单是 `en, ja, zh, zh-hant`;(c) 保持标点与语气一致。
**(a) 与 (c) 成立且与代码意图一致;(b) 被代码证伪**:`apps/desktop/src/i18n/types.ts:8` 的 `Locale` 有 5 个 id,
`ar` 同样是一等 locale(在 `apps/desktop/src/i18n/catalog.ts:8`、`LOCALE_OPTIONS`、`RTL_LOCALES` 里都在)。
名单自称是 "all locales" 却漏了一个,末句 "across all four" 也是字面为假(实为五)——
**这是 ▲ 不是 ◎**,因为照着做的人会漏掉 `ar`。§2.2 的数据显示**这正是已经发生的事**:
`ar` 覆盖率 78.7%,是 5 个语言里最低的。

### ▲-2 同一份文档的提交前清单重复了同一个漏数

`apps/desktop/DESIGN.md:334 @ 863e313`(归 `apps/desktop/DESIGN.md:315` 的
`## Before you add something — checklist` 标题管)

> - [ ] All four locales updated for any new/changed string?

与 ▲-1 同源但**归属另一个标题**,故单列。这一条尤其要紧:它是**提交前逐项打勾的清单**,
是最后一道人工关卡,而它把关卡本身设成了 4/5。

### ▲-3 「每个用户可见字符串都走 `useI18n()`」漏掉了第二个翻译器

`apps/desktop/DESIGN.md:285 @ 863e313`

> - Every user-facing string goes through `useI18n()` (`src/i18n/context.tsx`).
>   No literals in JSX.

前半句是**全称断言**且点名了具体机制。代码里存在**第二个并列的翻译器** `translateNow`
(`apps/desktop/src/i18n/runtime.ts:64`),**129 个调用点、24 个文件**(§2.3 有枚举命令),
它不经过 `useI18n()`,存在的理由恰恰是 store / handler 拿不到 React context——
`runtime.ts` 的注释自己写明了这一点:

`apps/desktop/src/i18n/runtime.ts:58 @ 863e313`

```ts
/** The locale module-level translators resolve against (the app's active
 *  `display.language`). Plugin `ctx.i18n.t` reads this too. */
export function getRuntimeI18nLocale(): Locale {
  return runtimeLocale
}
```

**判定 ▲,但范围要写准**:被证伪的是「唯一入口是 `useI18n()`」这个机制指认,
**不是**「不要硬编码字符串」这个意图——后者仍然成立,`translateNow` 也是走 i18n 的。

### ◇-1 插件 i18n 这套 API 在官方文档里不存在

`apps/desktop/src/i18n/plugin-i18n.ts` 整整 116 行、4 个导出符号
(`createPluginI18n` / `registerPluginLocales` / `translatePlugin` / `usePluginI18n`),
经门面对外暴露:

`apps/desktop/src/i18n/index.ts:19 @ 863e313`

```ts
export {
  createPluginI18n,
  type PluginI18n,
  type PluginLocaleBundles,
  type PluginMessages,
  type PluginMessageValue,
  type PluginTranslate,
  registerPluginLocales,
  translatePlugin,
  usePluginI18n
} from './plugin-i18n'
```

并进一步经插件 SDK 门面转出:

`apps/desktop/src/sdk/index.ts:221 @ 863e313`

```ts
/** Localized copy. `useI18n` reuses the app's strings; `usePluginI18n(id)` +
 *  `ctx.i18n.register` let a plugin ship its OWN locale bundles, scoped like
 *  `ctx.storage` and resolved against the app's active locale — no core edit. */
```

而插件 SDK 文档只提了 `useI18n`:

`website/docs/developer-guide/desktop-plugin-sdk.md:450 @ 863e313`

> `useI18n` (localized copy — your plugin stays translatable), and

**照文档做的插件作者只能读到 app 的核心字符串,没有任何途径给自己的界面配翻译。**

**搜索面**(负结论要付的成本):在**全仓所有 `.md` / `.mdx`** 上搜
`usePluginI18n|registerPluginLocales|createPluginI18n|translatePlugin`
(`grep -rn --include=*.md --include=*.mdx`,排除 `node_modules`),**全仓仅 1 处命中**,
在这里——

`skills/autonomous-ai-agents/hermes-agent/references/desktop-plugins.md:84 @ 863e313`

> interpolator functions; nested trees are addressed by dot-path. Read them
> reactively in components with `usePluginI18n(id)` returning `t('key', ...args)`
> (re-renders on a locale switch), or via `ctx.i18n.t` in handlers/stores.

——一个 skill 参考文件,**不在派工书 §4 列的文档来源清单内**
(`README.md` / 根 `AGENTS.md` / `apps/desktop/{AGENTS,DESIGN,README}.md` / `website/docs/**`)。
即:**在官方文档面里是 0 命中**;那唯一一处旁证内容准确,但插件作者不会在那儿找 SDK 文档。

### ◎-1 `AGENTS.md` 的说法反而没有踩坑

`apps/desktop/AGENTS.md:199 @ 863e313`

> - Does the change pass the [`DESIGN.md`](./DESIGN.md) checklist and update all
>   locales?

它说 "all locales" 而**不枚举**,字面为真、随 locale 增减自动保持正确。
记 ◎ 是为了留一条对照:**同一个仓库里,不枚举的写法活下来了,枚举的写法(▲-1/▲-2)烂了。**

---

## 6. 缺陷

### ■-1 `zh` 缺 20 个键,其中 4 个在中文界面上显示为原始 action id

完整链条见 §3,不重复。要点:

- `zh.ts` 是 `: Translations` 直标注,**不走 `defineLocale` 兜底**;
- 缺的 20 个键**全部**落在 `Record<string, string>` 开放桶里(`keybinds.actions` 4 个、
  `settings.fieldLabels` 3 个、`settings.fieldDescriptions` 13 个),所以 tsc 不报;
- 用户可见后果:中文「设置 → 快捷键」里 4 个终端 action 显示 `view.newTerminal` 这类原始 id;
  另外 16 个是设置项的标签/说明缺失,回落到英文兜底(这 16 个因此只是显示英文,不显示 id):

`apps/desktop/src/app/settings/config-field.tsx:47 @ 863e313`

```tsx
  const label =
    fieldCopyForSchemaKey(t.settings.fieldLabels, schemaKey) ??
    fieldCopyForSchemaKey(FIELD_LABELS, schemaKey) ??
    prettyName(schemaKey.split('.').pop() ?? schemaKey)
```


**严重度:低(仅显示层),但它是一类系统性风险的实例**——见 ■-2。

### ■-2 类型契约有 512 个位置不受 tsc 保护,且无任何补偿机制

`Translations` 枚举了 2,251 个叶子槽位,`en` 实际写下 2,763 个,差额 **512** 全在
`Record<string, string>` 之类的开放桶里(数与命令见 §2.3)。这些位置:

- tsc **不检查**跨 locale 的键齐整性;
- 运行时**不告警**(§4.3 的搜索面);
- **没有跨 locale 的键平价测试**兜底。

作者显然撞见过这个形状并**局部**修过一次:

`apps/desktop/src/components/find-bar.test.tsx:224 @ 863e313`

```tsx
  it('every registered find action has an i18n label (keybinds panel row)', () => {
    for (const id of ['view.findInPage', 'view.findNext', 'view.findPrevious']) {
      expect(en.keybinds.actions[id], id).toBeTruthy()
      expect(zh.keybinds.actions[id], id).toBeTruthy()
    }
  })
```

这个用例只覆盖 **3 个硬编码 id、2 个 locale**;`view.newTerminal` 那 4 个就在同一个
`keybinds.actions` 桶里,只是不在这份名单上,于是 ■-1 活了下来。

**可迁移的教训**:把「字符串表齐整性」交给类型系统,只在类型**枚举**了键时成立。
一旦用 `Record<string, string>` 换取灵活性,就必须**同时**补一条按数据驱动的平价测试
(遍历 `KEYBIND_ACTION_IDS` × 全部 locale),否则灵活性是白拿的,代价记在用户界面上。
现成的枚举源已经存在:

`apps/desktop/src/lib/keybinds/actions.ts:157 @ 863e313`

```ts
export const KEYBIND_ACTION_IDS: readonly string[] = KEYBIND_ACTIONS.map(action => action.id)
```


---

## 7. 测试(行为规格)

`apps/desktop/src/i18n/` 下 4 个测试文件(LT 层,不计入本片 13 文件):

```verify
cd /home/user/r10b-ts/hermes-agent/apps/desktop && npx vitest run --project ui src/i18n/
```

```console
 Test Files  4 passed (4)
      Tests  28 passed (28)
```

**passed 28 / failed 0 / skipped 0。**

**零执行点名**:无。`grep -rn "\.skip\|\.todo\|\.only" /home/user/hermes-agent/apps/desktop/src/i18n/*.test.*`
零命中;`--reporter=verbose` 逐条列出 28 个 `✓`,与汇总数一致,无整文件跳过、无收集错误。

按文件(`--reporter=verbose` 逐条计数):`apps/desktop/src/i18n/context.test.tsx` 11 ·
`apps/desktop/src/i18n/runtime.test.ts` 7 · `apps/desktop/src/i18n/plugin-i18n.test.tsx` 6 ·
`apps/desktop/src/i18n/languages.test.ts` 4 = **28**,与汇总数一致。

值得记下的几条行为契约(用例名即规格):

| 用例(文件:行) | 钉住的行为 |
|---|---|
| `apps/desktop/src/i18n/runtime.test.ts:71` 的 `returns the key when no locale can resolve a path` | 三级回落的末级:返回原始 key 字符串 |
| `apps/desktop/src/i18n/runtime.test.ts:56` 的 `falls back to English when the active locale cannot resolve a key` | 用例**运行时把 `TRANSLATIONS.ja.boot.ready` 改成 `undefined`** 再断言回落到英文——直接演示了「包不全会怎样」 |
| `apps/desktop/src/i18n/runtime.test.ts:49` 的 `keeps translated settings field copy addressable from schema keys` | snake_case schema 键 → camelCase 文案键的转换(§4.5) |
| `apps/desktop/src/i18n/context.test.tsx` 的 `does not overwrite unsupported configured languages` | 配置里存着不认识的语言值时,**不把它改写掉**,只是显示英文 |
| `apps/desktop/src/i18n/context.test.tsx` 的 `applies RTL direction for Arabic and restores LTR on switch back` | `dir=rtl` 的设置与还原 |
| `apps/desktop/src/i18n/context.test.tsx` 的 `rolls back the visible locale when saving fails` | 保存失败时界面语言回滚到旧值(`apps/desktop/src/i18n/context.tsx:167`) |
| `apps/desktop/src/i18n/plugin-i18n.test.tsx` 的 `scopes bundles per plugin — no cross-read` | 插件间键空间隔离(§4.6) |

**测试没有覆盖的**:跨 locale 的键齐整性(■-2)。28 个用例里没有任何一条遍历 `TRANSLATIONS`
比较各 locale 的键集合。

---

## 8. 判据自查(L3-1 ~ L3-5)

| 判据 | 自评 | 依据 |
|---|---|---|
| **L3-1 用途到位** | **达标** | §0 两张表覆盖 13 个文件,每个都是**全路径** + 「它是什么、谁读它」。数据表 5 个虽同型归组,组内仍逐个列全路径与行数 |
| **L3-2 形态账** | **达标** | §2 分三种形态(数据表 / 类型契约 / 运行时装配),各给文件数与行数(§2.1 命令)、叶子键规模与逐语言覆盖率(§2.2 探针 + 命令)、其他 5 个规模数(§2.3 命令)。**每个数都附了得出它的命令,且全部实测复现过** |
| **L3-3 一条真链** | **达标** | §3 七跳,从 `catalog.ts` 总装 → `defineLocale` 合并 → `I18nProvider` 装配 → `t` 直接访问 → 类型开放桶 → en/zh 键差 → 设置页显示原始 id。逐跳带锚点,末端是可见现象 |
| **L3-4 逐字取证下限(≥2 且钉在链上)** | **达标(12 块,超下限 6 倍)** | §3 那条链的 7 跳全部带逐字块:跳 1 `apps/desktop/src/i18n/catalog.ts:8`:`export const TRANSLATIONS: Record<Locale, Translations> = {`;跳 2 `apps/desktop/src/i18n/define-locale.ts:39`:`export function defineLocale(overrides: TranslationOverrides): Translations {` 与 `apps/desktop/src/i18n/zh.ts:5`:`export const zh: Translations = {`;跳 3 `apps/desktop/src/i18n/context.tsx:104`:`useEffect(() => {` 与 `apps/desktop/src/main.tsx:53`:`<I18nProvider>`;跳 4 `apps/desktop/src/i18n/context.tsx:178`:`const value = useMemo<I18nContextValue>(`;跳 5 `apps/desktop/src/i18n/types.ts:262`:`categories: Record<string, string>`;跳 6 `apps/desktop/src/i18n/en.ts:263`:`'view.showFiles': 'Show file browser',` 与 `apps/desktop/src/i18n/zh.ts:258`:`'view.showFiles': '显示文件浏览器',`;跳 7 `apps/desktop/src/app/settings/keybind-settings.tsx:203`:`const label = k.actions[action.id] ?? action.label ?? action.id`、`apps/desktop/src/components/ui/tooltip.tsx:216`:`function TipKeybindLabel({ actionId, text }: TipKeybindLabelProps) {`、`apps/desktop/src/app/command-palette/index.tsx:765`:`id: 'nav-new-window',`。**均为链上的跳,非随手摘数据表** |
| **L3-5 记号或带搜索面的负结论** | **达标** | ▲ 3 条(▲-1/▲-2 分属不同标题,▲-3 范围已写准)、◇ 1 条、◎ 1 条、■ 2 条,均带锚点。两条负结论均附搜索面:§4.3「回落路径零日志」(8 个文件 × 10 个模式,并说明唯二命中为何不算)、§5 ◇-1「官方文档零覆盖」(全仓 .md/.mdx,说明唯一命中在清单外的 skill 文件) |

**未达标项:无。** 一处主动降级说明:§2.2 的覆盖率是**静态解析**的authored 键,
不是运行时求值结果——探针不执行代码、不解析 import(`en` 的两棵子树是**单独解析 `constants.ts`
后接回来的**,已在探针注释与 §2.2 正文写明)。若某个包用了本探针不认识的动态构造,
会体现在 `opaque` 列;当前实测 5 个包 `opaque` 全为 0,故该口径下的数是完备的。

---

## 9. 移交项

| 编号 | 锚点 + 现象 | 建议 |
|---|---|---|
| **H-R10B-I-a** | `apps/desktop/src/i18n/zh.ts:258` 的 `'view.showTerminal': '显示终端',` —— 紧接其后 `apps/desktop/src/i18n/en.ts:263-268` 的 4 个终端 action 键在 zh 中不存在,中文设置页显示原始 id | 属 ■-1。若后续轮做「缺陷清单」,这是一条可直接复现的样本 |
| **H-R10B-I-b** | `apps/desktop/src/app/command-palette/index.tsx:767`:`label: t.keybinds.actions['session.newWindow'],` —— 全 app **唯一**一处读 `keybinds.actions` 却**不写 `??` 兜底**的调用点;该键当前 5 个 locale 都有,故暂不触发 | 值得核一遍:是有意为之(该键有平价保证)还是遗漏。其余 6 处调用点全部写了兜底:`apps/desktop/src/components/ui/tooltip.tsx:220`、`apps/desktop/src/components/find-bar.tsx:168,172`、`apps/desktop/src/app/settings/keybind-settings.tsx:76,90,203,263` |
| **H-R10B-I-c** | `apps/desktop/src/lib/keybinds/actions.ts:157`:`export const KEYBIND_ACTION_IDS: readonly string[] = KEYBIND_ACTIONS.map(action => action.id)` —— 一份现成的 action id 全集,可直接用来写「所有 locale × 所有 action 都有标签」的平价测试,补 ■-2 的口子 | 这是 ■-2 最小成本的修法,不需要改类型 |
| **H-R10B-I-d** | `apps/desktop/src/i18n/context.tsx:58`:`const RTL_LOCALES = new Set<Locale>(['ar'])` —— RTL 名单**不在** `languages.ts` 的 locale 元数据里,是加 locale 时第 6 个必改点且无编译器保护(§4.2 表) | 若后续轮写「桌面端可扩展点」章,这是「元数据被拆到两个文件」的现成例子 |
| **H-R10B-I-e** | `apps/desktop/src/main.tsx:53` 的 `<I18nProvider>` —— 挂载时**不传 `initialLocale`**,故首帧必为 `en` + `dir=ltr`,配置异步读回后才切换;阿拉伯语用户开机会看到一次 LTR→RTL 翻转 | 本片未测量翻转的可感知程度(需要真 Electron 启动)。属**未取证的观察**,不作结论,留给做启动路径的轮次 |
| **H-R10B-I-f** | `apps/desktop/DESIGN.md:334`:`- [ ] All four locales updated for any new/changed string?` —— 提交前清单把 5 个 locale 写成 4 个(▲-2) | 若项目后续汇总「文档腐烂」跨轮指标,这条与 ▲-1 同源但归属不同标题,计数时按 2 条还是 1 条需统一口径 |

---

## 10. 本片成本自报(L3 首个数据点)

```text
片号            : I
层              : L3
文件数 / 行数   : 13 / 17,378
实际打开的文件数: 27   (片内 13 全部触及,其中 7 个装配件逐行读完;
                        片外 14 个为追「谁读它 / 缺了会怎样」而打开)
实际读过的行数  : ~1,070  (≈ 6% of 17,378)
主观耗费        : 中
```

**「实际读过的行数」的估法**(派工书特别要求说明):按**人眼逐行读过**计,不含探针机器解析的行。

| 来源 | 行数 | 估法 |
|---|---:|---|
| 7 个装配件全文 | 567 | 精确(整目录 `Read`,无截断) |
| `types.ts` + 5 个语言包 | ~210 | 估算:每个文件 head/tail 各 ~14 行 × 6 = ~170,加定向 `sed`/`grep` 命中区域 ~40 行 |
| 片外文件片段 | ~293 | `field-copy.ts` 57(全文)、`runtime.test.ts` 75(全文)、`main.tsx` 36、`DESIGN.md` ~30、`keybind-settings.tsx` ~15、`tooltip.tsx` ~25、`sdk/index.ts` 13、`find-bar.test.tsx` ~18、其余 6 个文件各 ~4 行 |
| **合计** | **~1,070** | |

**16,811 行的数据表 + 类型契约里,人眼只读了约 210 行(1.2%)**,其余全部由一个 AST 探针
一次性算成 §2.2 那张表。**这正是 L3 与 L2 的成本分野**。

**瓶颈在哪**(三条,按耗时降序):

1. **不在行数上,在「写一个算得对的探针」上。** 第一版探针把 `en.ts` 的
   `fieldLabels: FIELD_LABELS`(一个跨文件 import)当成 1 个不透明节点,于是 `en` 报 2,625 而
   `zh` 报 2,762,**看上去像「中文比英文多译了 137 条」**——完全是假象。必须额外解析片外的
   `apps/desktop/src/app/settings/constants.ts` 把两棵子树接回来,五个包才可比。
   **L3 片的规模数只要跨文件引用一次,天真计数就会给出反向结论**,这个坑要预算进去。
2. **「缺了会怎样」这一问的答案全在片外。** 片内 13 个文件能回答「有什么、有多大」,
   但 L3-3 要的那条链有 4 跳(`keybind-settings.tsx` / `tooltip.tsx` / `config-field.tsx` /
   `command-palette/index.tsx`)**一个都不在片里**。追链打开了 14 个片外文件。
3. **概念密度低,跨文件核对多。** 单个机制都不难(合并、查表、context),难的是把
   「4 个 locale 集合是否相等」「512 个键为什么不受保护」这类**需要交叉三四个文件才能下结论**的问题坐实。
   期间否定了 2 个错误怀疑(§4.4 `platformIntro`、§4.5 `ar` 的扁平写法),
   **两次都是「数字看着像缺陷、读了代码是设计」**——这部分时间无产出但不可省。

**给 R11B 排期的建议(787 文件 / 263,763 行 L3):**

- **不要按行数估 L3 工作量。** 本片 82% 的行数(数据表)消耗了不到 10% 的时间。
  建议改用两个量:**(a) 非数据文件数**(本片 8 个:7 装配 + 1 契约),
  **(b) 为答「谁读它」必须打开的片外文件数**(本片 14 个)。本片 ≈ 22 个「有效文件」。
- **同型数据表要在切片时就识别出来并配探针预算。** 一片里若有 N 个同构数据文件,
  成本是「写一个探针」而不是「读 N 个文件」——但这个探针**平均要迭代两次**才算得对(见瓶颈 1)。
- **L3-3 那条链决定了片外读量。** 切片时若能顺带标出「本片产物的主要消费者在哪几个文件」,
  可以省掉这一片里最费时的一段搜索。

---

## 附:本片新增资产

- `data/r10b/probes/probe_i_leafkeys.mjs` —— 用 TypeScript 官方 parser 静态统计 5 个语言包
  与 `Translations` 契约的叶子键;`--paths <locale>.ts` 输出该 locale 全部叶子路径供 `comm` 对账。
  **只依赖 `typescript` 包**,用 `NODE_PATH` 指向任一装了它的 checkout 即可;不执行被测代码、
  不写基线。开头三段注释写明了 leaf / opaque / call 三个口径的定义。
