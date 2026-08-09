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

---

## 复核 2:■-R10-01 在桌面渲染进程里**没有孪生**(有搜索面的负结论)

R10 立的 ■-R10-01 是:dashboard 的 plugin manifest `external_dependencies[].install`
字段以 `shell=True` 交给 `_run_setup_command`,无过滤。派工时我给片 H 的提示是
「桌面端装插件走的是同一条路还是另一条?」。主线在片 H 到货**之前**独立查了一遍,
先把答案落在这里,以便与片 H 的结论互相对照而不是互相污染。

**结论:本轮范围内(`apps/desktop/src/` + `apps/shared/src/`)没有这条路。渲染进程一次 shell 都不开。**

### 2.1 搜索面

第一面 —— manifest 的那几个字段名:

```verify
cd /home/user/hermes-agent && grep -rn "external_dependencies\|externalDependencies\|install_cmd\|installCmd" \
  apps/desktop/src apps/shared/src 2>/dev/null | wc -l
```

```text
0
```

第二面 —— 任何形式的进程启动。**这一条我先做错了一次,把改正过程留在这里**:
初稿写的是一条带 `grep -cv` 排除项的命令并声称输出 `0`,而我实际只看过未过滤列表的
**前 12 行**(`head -12`)就下了结论。重跑真实输出是 **17**,不是 0。
——这正是本项目反复记的那个形状:**把截断当成全貌**。改为逐条列出全部 17 处:

```verify
cd /home/user/hermes-agent && grep -rnE "spawn\(|exec\(|execFile\(|shell: *true" apps/desktop/src \
  --include=*.ts --include=*.tsx | grep -v "\.test\." | grep -vE "\.exec\(|function spawn\(|spawn\(cfg" | wc -l
```

```text
17
```

**17 处逐条查过,没有一处是启动进程**:

- **16 处在 `apps/desktop/src/lib/desktop-slash-commands.ts`**,是同一个本地工厂函数的调用。
  它返回一个**描述符**,不执行任何东西:

  `apps/desktop/src/lib/desktop-slash-commands.ts:137 @ 863e313`

  ```ts
  const exec = (): DesktopCommandSurface => ({ kind: 'exec' })
  ```

  `surface: exec()` 的意思是「这条斜杠命令由网关侧执行」,是一行元数据。
  (16 处里还有 1 处是注释里提到 `exec()`。)

- **1 处在 `apps/desktop/src/store/hub-actions.ts:74`** 的 `await spawn()`,而 `spawn`
  是这个函数自己的**形参名**,由调用方传进来的回调:

  `apps/desktop/src/store/hub-actions.ts:66 @ 863e313`

  ```ts
  async function runHubAction(key: string, kind: HubActionKind, spawn: () => Promise<{ name: string }>): Promise<void> {
  ```

**排除项也要说清楚**:上面命令去掉的是 `RegExp.prototype.exec`(渲染层大量用它做文本匹配)、
`components/particles/particle-field.tsx` 里那个叫 `spawn` 的**粒子生成函数**,
以及 `*.test.*`。**剔除项 + 逐条查证的 17 处,合起来才是完整的搜索面。**

### 2.2 但负结论要带上它的边界:渲染进程有 72 个 IPC 出口

「渲染层不开进程」不等于「渲染层不能让别人开进程」。它对外只有一座桥:

```verify
cd /home/user/hermes-agent && grep -rhoE "window\.hermesDesktop\??\.[a-zA-Z_]+" apps/desktop/src \
  --include=*.ts --include=*.tsx | sed 's/.*\.//' | sort -u | wc -l
```

```text
72
```

72 个成员里,**`terminal` 这一个就是专门用来执行命令的**
(`apps/desktop/src/app/right-sidebar/terminal/use-terminal-session.ts`,右侧栏的终端面板),
另有 `openExternal` / `revealPath` / `openDir` / `uninstall` / `repairBootstrap` /
`resetBootstrap` 这些会落到主进程的动作。**所以正确的表述是:**

> 渲染进程自己不开进程;能不能开、开什么,由主进程 `apps/desktop/electron/` 那 72 个通道的
> 实现决定——而那部分是 **R10 片 H 的范围**,本轮不重读。

R10 片 H 已就 Electron IPC 记过一条:`fs:reveal` / `openDir` / `rename` / `trash`
绕过 `hardening.ts`,同组另 6 条都过。**本复核与那条不冲突,是它的另一侧**:
本轮证明的是「危险不在渲染层」,R10 证明的是「危险在通道实现的守卫一致性上」。
两条合起来支持 R10 的那句可迁移形式——**守卫要绑在收口点,不是绑在每条缝的入口**。

*不主张的部分*:本复核**没有**重验那 72 个通道各自的实现,也**没有**判断 `terminal`
通道有没有审批闸。那两件事都在 R10 已读过的 `apps/desktop/electron/` 里。

---

## 复核 3:片 K 的供应链结论 —— **独立佐证**,但它对 Rust 测试的判断**被推翻**

### 3.1 推翻的部分:Rust 测试跑得了,而且全绿

片 K 写:「Rust 51 个 `#[test]` 未跑(**无工具链**、跑 cargo 会**污染基线**)」。
**两半都不成立。**

工具链在:

```verify
which cargo rustc
```

```text
/root/.cargo/bin/cargo
/root/.cargo/bin/rustc
```

而「跑 cargo 会污染基线」这个顾虑正确、结论错误:**不在基线里跑就行**。
主线在 `git archive` 导出的副本里跑,基线全程 `git status --porcelain` 为空。
结果 **51 passed / 0 failed / 0 ignored / 0 filtered**(详见 `notes/r10b-96-tests.md` §5.1),
是本项目十轮以来第一次运行这个 crate 的测试。

*这条值得记的地方不在于片 K 少跑了一个套件,而在于**它把一个可测的事实写成了断言**。*
派工书里明写了环境在哪、可以跑测试;片 K 的两条理由**都可以用一条命令证伪**,而它没跑那条命令。
与 R10 那条「490 个测试要 Electron」是同一个形状:**推断出来的障碍和实测出来的障碍,长得一模一样。**
本轮在同一份产出里同时看到这个形状的**两次**(R10 的、片 K 的),它不是偶发。

### 3.2 佐证的部分:供应链的三条,主线独立搜过,与片 K 一致

主线在片 K 到货**之前**独立搜过安装器的完整性校验面,结论与它一致:

```verify
cd /home/user/hermes-agent/apps/bootstrap-installer/src-tauri/src && \
  grep -rniE "sha256|sha512|checksum|signature|minisign|gpg|digest" *.rs | wc -l
```

```text
0
```

```verify
cd /home/user/hermes-agent/apps/bootstrap-installer/src-tauri/src && \
  grep -rnoE "https://[a-zA-Z0-9./_{}-]+" *.rs | sort -u
```

```text
install_script.rs:327:https://raw.githubusercontent.com/NousResearch/hermes-agent/{}/scripts/{}
```

**只有一个出网点,零校验。** 下载的是要在用户机器上执行的安装脚本:

`apps/bootstrap-installer/src-tauri/src/install_script.rs:325-329 @ 863e313`

```rust
async fn download(kind: ScriptKind, commit_or_ref: &str, dest_path: &Path) -> Result<()> {
    let url = format!(
        "https://raw.githubusercontent.com/NousResearch/hermes-agent/{}/scripts/{}",
        commit_or_ref,
        kind.filename()
```

而片 K 点出的那处「唯一叫 `verify` 的代码反而把失败抹掉」,主线逐字核过,成立:

`apps/bootstrap-installer/src-tauri/src/paths.rs:142-152 @ 863e313`

```rust
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

**验签失败 → 用 ad-hoc 身份重新自签。** 这不是校验,是把校验的失败分支填平。
`let _ =` 还把重签本身的失败也丢掉了。

依赖锁被忽略这条也成立:

`apps/bootstrap-installer/.gitignore:1-3 @ 863e313`

```gitignore
# Rust / Cargo
/src-tauri/target/
/src-tauri/Cargo.lock
```

**主线补一条片 K 没说的**:`Cargo.lock` 不入库,意味着**本轮跑出来的那 51 个绿灯,
用的依赖版本与作者机器上的可能不是同一批**。测试全绿这件事的强度,因此比看上去弱一档——
它证明的是「今天解析出的这套依赖下代码是对的」,不是「作者发布的那套依赖下代码是对的」。
*这一条削弱的是我自己上一节的战果,所以更要写。*

### 3.3 副产品:又一个「连锚点都不算」的形态 —— 无扩展名路径

片 K 的 ■-1 锚在 `apps/bootstrap-installer/.gitignore:3`。**这个锚点不会被校验器识别**:
本轮扩了扩展名白名单,但 `.gitignore` / `Dockerfile` / `Makefile` 这类**根本没有扩展名**
的文件,白名单这个机制在原理上就覆盖不到。全语料实测:

```verify
python3 data/r10b/probes/extless_anchor_scan.py | tail -5
```

```text
corpus excludes: ('r10b-', 'round-10b-')
resolvable extensionless anchors NOT recognised by the whitelist:
  x17  .gitignore   in: 15 个文件
  x2  Dockerfile   in: round-1-capabilities-full.md, round-1-survey.md
total occurrences: 19  distinct paths: 2
```

**两个读数分开报**(这个探针也躲不过测量污染——本节自己就引用了
`apps/bootstrap-installer/.gitignore`):**剔除本轮写作 19 处 / 2 个路径**;
不剔除(`--no-exclude`)**25 处 / 3 个路径**。报告采用前者。

*这已经是本轮第三次撞见同一个形状了*(`named_coverage`、`cite_ext_scan`、这里)。
H-R9D-e 当初把它记成「点名覆盖率这个测量对报告它不幂等」——**实际它是所有
扫语料的探针的共同性质**,不是那一个测量的毛病。三次里有两次是本轮自己新写的探针,
说明这不是历史包袱,是**每写一个扫语料的探针就会重新长出来的东西**。已提炼为移交项。

**22 处,可解析,但既不校验也不计 UNCHECKED** —— 与 H-R10-a 同一个家族。
**本轮不修**:纪律是「开工杂项若需改动 `scripts/`,须在派发子代理之前完成」,
而这是子代理运行期间发现的;而且它的修法与扩展名白名单不同(要一份显式的
无扩展名文件名单,不能靠正则放宽,否则 `word:数字` 满地都是)。**带证据移交 R11A。**

*上面那 3 处 `.gitignore:1-3` 的锚点,主线是人工核对的*(`sed -n '1,3p'`),
因为关卡读不到它——**这句话本身就是这条移交项的理由**。
