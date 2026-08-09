# r10b · 测试作为行为规格 —— 底稿

> 溯源约定:锚点写作 `路径:行号 @ 863e313`,**单独成行、置于代码块之前**。
> 本节报数一律 **passed / failed / skipped 三个数**,并逐个点名整文件跳过与零执行。

## 0. 先说一句:本轮范围里没有一个 Python 文件

R10B 的 977 个文件全在 `apps/desktop` / `apps/bootstrap-installer` / `apps/shared` 下,
`kind` 是 ts/tsx/rs/json/css/md。**Python 测试对本轮是旁证,不是范围内测试。**
但它们仍然值得跑——桌面端的构建与安装脚本有 Python 侧的对账测试。

## 1. R10 的「490 个测试一个都没跑」要改述,而且改述之后是好消息

R10 报告 §7.2 写:「`apps/desktop` 的 **490 个测试文件一个都没跑**(需 Electron 运行时,
本容器装不动)……**R10 范围内行数最大的一块,执行验证是空白的**」。

**其中 471 个不需要 Electron,本轮全部跑了。** 根据是被测仓库自己的配置:

`apps/desktop/vitest.config.ts:6-11 @ 863e313`

```ts
  test: {
    name: 'ui',
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    globals: true,
```

`apps/desktop/vitest.config.ts:20-24 @ 863e313`

```ts
const electronNative: TestProjectConfiguration = {
  test: {
    name: 'electron',
    environment: 'node',
    include: ['electron/**/*.test.ts', 'scripts/**.test.{ts,mjs}']
  }
```

两个 project,一个 `jsdom` 一个 `node`,**都不是 Electron 二进制**。
只有 `e2e/` 的 Playwright spec 需要真 Electron + 浏览器。

**并且本轮的运行环境里确实没有 Electron 二进制**——建环境时显式跳过了它的下载
(`ELECTRON_SKIP_BINARY_DOWNLOAD=1`,见 `data/r10b/probes/ts_test_env.sh`),
所以「跑通了」不可能是偷偷用了 Electron:

```verify
ls /home/user/r10b-ts/hermes-agent/node_modules/electron/dist/electron 2>/dev/null \
  && echo PRESENT || echo "ABSENT (ELECTRON_SKIP_BINARY_DOWNLOAD=1)"
```

```text
ABSENT (ELECTRON_SKIP_BINARY_DOWNLOAD=1)
```

### 1.1 490 这个数怎么来的,以及它漏了什么

```verify
cd /home/user/hermes-agent/apps/desktop && \
  printf "all *.test.*/*.spec.* : %s\n" "$(find . -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.test.mjs' -o -name '*.spec.ts' | wc -l)" && \
  printf "  ui   src/**          : %s\n" "$(find src -name '*.test.ts' -o -name '*.test.tsx' | wc -l)" && \
  printf "  el   electron/**     : %s\n" "$(find electron -name '*.test.ts' | wc -l)" && \
  printf "  el   scripts/*.test.*: %s\n" "$(ls scripts/*.test.ts scripts/*.test.mjs 2>/dev/null | wc -l)" && \
  printf "  e2e  e2e/*.spec.ts   : %s\n" "$(ls e2e/*.spec.ts | wc -l)"
```

```text
all *.test.*/*.spec.* : 494
  ui   src/**          : 396
  el   electron/**     : 75
  el   scripts/*.test.*: 4
  e2e  e2e/*.spec.ts   : 19
```

**三个读数,分别标注,不合并**:

| 读数 | 值 | 口径 |
|---|---|---|
| 全部测试文件 | **494** | `apps/desktop` 下所有 `*.test.*` / `*.spec.*` |
| R10 报的 | **490** | = 396 + 75 + 19,**漏了 `scripts/*.test.{ts,mjs}` 那 4 个** |
| 本轮实跑 | **475** | = 396 + 75 + 4;未跑的是 e2e 的 19 个 |

**按 R10 自己的分母算:490 里跑了 471 个(96.1%),没跑的正好是那 19 个 Playwright spec。**
R10 那句话的**结论方向**是对的(e2e 确实跑不了),**范围**错了 20 倍多。

*为什么会错*:「桌面端 = Electron = 要 Electron 运行时」是一个很自然的推断,
而它没有被 `vitest.config.ts` 核对过。这与本项目反复记的那条同型:
**推断出来的障碍和实测出来的障碍,在报告里长得一模一样。**

## 2. 逐套件报数

| 套件 | 文件 | passed | failed | **skipped** | 整文件跳过/零执行 |
|---|---|---|---|---|---|
| `apps/desktop` project=`ui`(jsdom) | 396 | **3,489** | 0 | **0** | 0 |
| `apps/desktop` project=`electron`(node) | 79 | **938** | 0 | **2** | **1**(点名见 §3) |
| `tests-js`(仓库根的跨包测试) | 3 | **9** | 0 | **0** | 0 |
| Python(与本轮范围有关的 8 个文件) | 8 | **599** | 0 | **0** | 0 |
| `apps/desktop/e2e`(Playwright) | 19 | — | — | — | **19 个全部未跑**(见 §4) |
| `apps/bootstrap-installer/src-tauri`(Rust) | 5 个含测试的源文件 | 见 §5 | | | |

```verify
grep -E "^##########|Test Files|Tests  " /home/user/hermes-study/data/r10b/measurements/desktop-vitest-summary.txt
```

```text
########## project=ui (jsdom) ##########
 Test Files  396 passed (396)
      Tests  3489 passed (3489)
########## project=electron (node) ##########
 Test Files  78 passed | 1 skipped (79)
      Tests  938 passed | 2 skipped (940)
```

*只摘计数行,不摘 `Duration` / `Start at`*:两者每次都不同,不是证据。
**这两套件各跑过两遍**——一遍在派发子代理之前,一遍在 11 个子代理并发运行期间。
**四个计数(396/3489、79/940)两遍逐字相同,而耗时差了近 3 倍**
(ui project:238.30s → 697.20s,机器被子代理占满)。
按「同一指标的多次测量须分别标注」记在此处:**计数相同,耗时不同**,
不能笼统说成「两次读数相同」。

## 3. 两条 skipped 全部点名,以及它们掩盖了多少

**合计掩盖 2 个用例,其中 1 个使整个文件报为 skipped。** 两条都是**声明式的门**
(平台门 / 环境门),不是静默零执行:

**(1) 整文件跳过 —— `apps/desktop/electron/windows-remote-live.test.ts`,掩盖 1 个用例。**

`apps/desktop/electron/windows-remote-live.test.ts:28-29 @ 863e313`

```ts
test.skipIf(!liveHost || !liveUser || !configuredHermes)(
  'live Windows remote lifecycle spawns, authenticates, reuses, and cleans exact ownership',
```

该文件只有这一个用例,且是 `test.skipIf(...)` 而非 `test(...)`,所以
`grep -c "^\s*test("` 数它是 **0** —— 静态清点会把它当成「没有测试的文件」。

**(2) 单用例跳过 —— `apps/desktop/electron/fs-read-dir.test.ts`,掩盖 1 个用例。**

`apps/desktop/electron/fs-read-dir.test.ts:188-190 @ 863e313`

```ts
test('readDirForIpc marks a Windows junction to a directory as a directory', async t => {
  if (process.platform !== 'win32') {
    t.skip('junctions are a Windows-specific symlink type')
```

**这两条与 R10 在 ACP 上撞见的形态正好相反,值得对照。** R10 记的是
「模块级 import 缺依赖 → 整文件**静默零执行**;函数级 import → 单用例**可见失败**。
一个响、一个哑」。这里两条**都是响的**:运行器把它们计进 `skipped`,并附了跳过理由。
**差别在于跳过是被声明的还是被撞上的**——`skipIf` / `t.skip()` 是作者写下的门,
收集期 ImportError 是撞上的墙。前者可数,后者只能靠点名文件数去反推。

## 4. 未跑的部分,如实申报

**`apps/desktop/e2e/` 的 19 个 Playwright spec 一个都没跑。** 它们要真 Electron 二进制
(本环境显式未下载)+ 浏览器。这 19 个是**桌面端唯一的端到端验证**,
片 K 关于打包/启动链路的结论**没有执行验证兜底**,只有静态阅读与单元测试。

*不要把这条读成「和 R10 一样」*:R10 的空白是 490 个文件,本轮的空白是 19 个。

## 5. Rust 侧:本项目第一次跑 `apps/bootstrap-installer`

安装器是 Tauri + Rust,**历轮从未跑过它的测试**。静态清点:

```verify
cd /home/user/hermes-agent/apps/bootstrap-installer/src-tauri && \
  printf "#[test]        : %s\n" "$(grep -rho '#\[test\]' src/ build.rs | wc -l)" && \
  printf "#[tokio::test] : %s\n" "$(grep -rho '#\[tokio::test\]' src/ build.rs | wc -l)" && \
  printf "#[cfg(test)] 模块: %s\n" "$(grep -rho '#\[cfg(test)\]' src/ build.rs | wc -l)"
```

```text
#[test]        : 45
#[tokio::test] : 6
#[cfg(test)] 模块: 5
```

**首次尝试失败,原因是环境而非代码**,记录在案:`cargo test --offline` 报
`no matching package named anyhow`(离线索引为空),换成联网后 crate 全部解析成功,
但构建在 `gdk-sys` 上失败——容器缺 Tauri 的 GTK 系统库:

```text
The system library `gdk-3.0` required by crate `gdk-sys` was not found.
```

**处置:装了系统库(见 §6 的资源账),重跑。** 结果见 §5.1。

### 5.1 运行结果:51 passed / 0 failed / 0 skipped

```verify
grep -E "^running [0-9]+ test|^test result|^CARGO_EXIT" /home/user/hermes-study/data/r10b/measurements/cargo-test-raw.txt
```

```text
running 51 tests
test result: ok. 51 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
running 0 tests
test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
running 0 tests
test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
CARGO_EXIT=0
```

**51 = 45 `#[test]` + 6 `#[tokio::test]`,与静态清点严格相等**——没有被 `#[ignore]`
或 feature 门挡掉的用例(`0 ignored` / `0 filtered out`)。
另两个 `running 0 tests` 分别是 `src/main.rs` 的二进制 target 与 doc-tests,
**不是零执行故障**:前者只有一个 `fn main`,后者仓库未写文档测试。

*这是本项目十轮以来第一次运行 `apps/bootstrap-installer` 的测试。*
它给片 K 关于安装器的结论提供了行为规格底座——而在此之前,
「安装器」这块 6,241 行在项目里从未有过任何执行验证。

## 6. 环境与资源账

| 资源 | 开工 | 收工 | 期间安装 |
|---|---|---|---|
| Python 共享 venv | **87**(`pip list` 87 / `dist-info` 87) | 见报告 | **0** |
| node(基线之外的副本) | 0 | **1,186** | 1,186,来源 npmjs.org,**在派发子代理之前**装好,触发场景 = 跑 `apps/desktop` 与 `tests-js` 的 vitest |
| 系统库(apt) | — | — | **`libgtk-3-dev` / `libwebkit2gtk-4.1-dev` / `libsoup-3.0-dev` / `libjavascriptcoregtk-4.1-dev` / `pkg-config`**,来源 Ubuntu archive,**在子代理运行期间**装的,触发场景 = `cargo test` 在 `gdk-sys` 上构建失败 |
| Rust crates | 0 | 见 `data/r10b/measurements/cargo-test-raw.txt` | 由 `cargo test` 拉取到 `~/.cargo`,来源 crates.io |

**关于那次 apt 安装,把话说全**:项目纪律写的是「子代理运行期间**不擅自装包扩 venv**」。
apt 装的是**系统库**,不进 venv、不进 node_modules,**不改变本报告里任何一个包数读数**
(venv 全程 87,已两次实测)。但它确实是**子代理运行期间对共享环境的一次改动**,
所以在这里点名,而不是藏在「跑通了」三个字后面。
**收益是 51 个此前从未跑过的 Rust 用例**;若认为这笔交易不划算,依据在这里,可以推翻。
