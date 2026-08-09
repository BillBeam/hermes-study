# r10b · 主线独立复核 —— 底稿

> 溯源约定:锚点写作 `路径:行号 @ 863e313`,**单独成行、置于代码块之前**。
> 本文件记录主线**不照抄子代理结论**、自己取证的复核。每条写明:子代理说了什么、
> 主线独立测到什么、两者关系是「一致 / 收窄 / 推翻 / 合成」。

## 复核 1:i18n 叶子键 —— 两个测量给出不同的数,而两个都对

### 1.1 两个读数,必须分别标注

片 I(L3)用 TypeScript 官方 parser 静态数**每个语言包文件写了多少键**;
主线在派工**之前**就独立写了一个探针,**加载运行时对象**数**每个语言暴露多少键**。
两者对 `en` / `zh` 完全一致,对另外三个**差得很远**:

| 包 | 片 I:文件里写了 | 主线:运行时暴露 | 写法 |
|---|---|---|---|
| `en` | 2,763 | 2,763 | 字面量 |
| `zh` | **2,762** | **2,762** | **字面量** |
| `ja` | 2,335 | **2,763** | `defineLocale()` |
| `zh-hant` | 2,335 | **2,763** | `defineLocale()` |
| `ar` | 2,181 | **2,769** | `defineLocale()` |

```verify
cd /home/user/hermes-study && bash data/r10b/probes/run_i18n_leafkeys.sh 2>&1 | head -8
```

```text
file            authoring        leaves  opaque  call-subtrees  spreads
en.ts           literal            2763       0              2        0
zh.ts           literal            2762       0              2        0
ja.ts           defineLocale()     2335       0              2        0
zh-hant.ts      defineLocale()     2335       0              2        0
ar.ts           defineLocale()     2181       0              0        0
types.ts        interface Translations   2251       0              0        0
```

```verify
cd /home/user/hermes-study && bash data/r10b/probes/run_i18n_parity.sh 2>&1 | grep -E "LEAF_COUNTS|DIFF_VS_EN"
```

```text
LEAF_COUNTS en=2763 zh=2762 zh-hant=2763 ja=2763 ar=2769
DIFF_VS_EN zh missing=20 extra=19 firstMissing=keybinds.actions.view.closeTerminal,keybinds.actions.view.newTerminal,keybinds.actions.view.nextTerminal firstExtra=messaging.platformIntro.api_server,messaging.platformIntro.bluebubbles,messaging.platformIntro.dingtalk
DIFF_VS_EN zh-hant missing=0 extra=0
DIFF_VS_EN ja missing=0 extra=0
DIFF_VS_EN ar missing=0 extra=6 firstExtra=keybinds.actions.view.closePreviewTab,onboarding.flowSubtitles.loopback,sidebar.nav.agents
```

**不是矛盾,是两个分母**:「作者翻译了多少」与「用户看到多少」。
片 I 量的是前者(它管这叫翻译覆盖率),主线量的是后者。
*一处必须交代*:主线这个探针是在派工**之前**写的,所以两个读数是**独立**的,
不是主线拿片 I 的答案去凑。

### 1.2 合成之后,结论比任何一个读数都强

**单看任一读数都会得出错误的排序:**

- 只看片 I 的静态数:`ja` 2,335 比 `zh` 2,762 少 427,**看起来日文翻译最差**。
- 只看主线的运行时数:`zh` 缺 20 个键、`ja` 缺 0 个,**能看出 zh 有问题,但看不出为什么**。

**合起来才看得见真正的形状:`zh` 是唯一没走 `defineLocale()` 的非英文包,
也是唯一在运行时真的缺键的包。** 保护另外三个的那套机制,恰好没有覆盖它。

`apps/desktop/src/i18n/define-locale.ts:39-41 @ 863e313`

```ts
export function defineLocale(overrides: TranslationOverrides): Translations {
  return mergeTranslations<Translations>(en, overrides)
}
```

`ja` / `zh-hant` / `ar` 都从这里出,漏译的键在构建期被 `en` 填上(所以运行时 0 缺失,
用户看到的是英文而不是空)。`zh` 不走这条路,它是一整个字面量:

`apps/desktop/src/i18n/zh.ts:5 @ 863e313`

```ts
export const zh: Translations = {
```

**那 tsc 为什么不报错?** 因为缺的那些键落在开放桶里:

`apps/desktop/src/i18n/types.ts:262-263 @ 863e313`

```ts
    categories: Record<string, string>
    actions: Record<string, string>
```

`Record<string, string>` 对「少了哪个键」毫无意见。缺的键在 `en` 里长这样:

`apps/desktop/src/i18n/en.ts:266-268 @ 863e313`

```ts
      'view.nextTerminal': 'Next terminal',
      'view.prevTerminal': 'Previous terminal',
      'view.closeTerminal': 'Close terminal',
```

**三件事必须同时成立,这个缺陷才出得来**:(a) 类型在这一段是开放桶,编译器不管;
(b) `zh` 是唯一不走构建期合并的非英文包,没有兜底;(c) 运行时回落是静默的
(片 I 已用 8 个文件 × 10 个模式的搜索面证明零日志、零 dev 警告)。
**去掉任何一条,中文用户都不会在「设置 → 快捷键」里看到 `view.newTerminal` 这种原始 id。**

**与片 I 的关系:一致,并且合成。** 片 I 的 ■-1 结论(zh 缺 20 键、4 个直接暴露原始 id)
主线独立复现;主线补上的是**为什么只有 zh**——片 I 把 `defineLocale` 当作解释
「ja/zh-hant/ar 为何数目小」的机制,没有反过来指出**它同时是 zh 独有缺陷的成因**。

### 1.3 顺带否掉一个我自己的初判

主线初看运行时数据时,把 `zh` 的 19 个 extra(`messaging.platformIntro.*`)
和 `ar` 的 6 个 extra 也当成了可疑项——「翻译包凭空多出 en 没有的键」。
**片 I 已经查过并否掉了**(`platformIntro` 是覆盖表,多出的键是合法的),
主线复核后同意:那一段类型就是 `Record<string, string>`(`types.ts:1239`),
**多键是这个设计允许的,不是缺陷**。记在这里是因为——
如果主线没读片 I 就自己下判断,会多报一条不成立的 ■。

### 1.4 语言集合严格相等,不记 ◇

```verify
cd /home/user/hermes-study && bash data/r10b/probes/run_i18n_parity.sh 2>&1 | grep "LOCALE_OPTIONS="
```

```text
LOCALE_OPTIONS=[ar,en,ja,zh,zh-hant] TRANSLATIONS=[ar,en,ja,zh,zh-hant] equal=true
```

派工书里问过「`languages.ts` 列的语言集合与实际语言包是否严格相等」。**相等,不记记号。**
