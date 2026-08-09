# r10-96 · TypeScript 测试套件的真实执行(主线)

> 本文件记录**主线**在基线之外的副本里真实跑通的 TS 套件。
> 子代理只做静态清点(派工书里明写不许跑 npm),两个口径的读数在 §3 分别标注,**不合并**。

---

## 1. 为什么要另建一个环境,以及它长什么样

R10 的范围是界面层,**它的行为规格大部分是 TypeScript 测试**——而基线里没有 `node_modules`。
装依赖必须解决两件事:不能碰基线;不能靠猜。

**不能碰基线**:R8A 有过一次教训 —— 子代理在基线里跑 npm,npm 重解析依赖改写了
`package-lock.json`(约 30 个条目被盖上 `"peer": true`)。它**恰好**被行数复核撞见;
若被改文件行数不变就会静默通过,而此后所有 `路径:行号 @ 863e313` 引用**全部失去意义**。
所以本轮用 `git archive` 把 `863e313` 导出到 `/home/user/r10-ts/hermes-agent`,在副本里装。
`git archive` 比 `cp -r` 好的地方是它只导出**已跟踪**文件,天然不带 `.git` 与 `node_modules`,
且导出内容就是那个 commit 本身。

脚本落库在 `data/r10/probes/ts_test_env.sh`,任何人 clone 下来可原样重跑:

```verify
bash data/r10/probes/ts_test_env.sh setup && bash data/r10/probes/ts_test_env.sh run
```

**不能靠猜:一次实测踩出来的结构事实。** 最初主线只复制 `ui-tui` 与 `web` 两个目录单独装,
得到的是这个:

```console
npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/@hermes%2fink - Not found
npm error 404  '@hermes/ink@0.0.1' is not in this registry.
```

报错点名 `@hermes/ink`,而真正的原因是**没有从仓库根装**。根 `package.json` 声明了 npm workspaces:

`package.json:6 @ 863e313`

```json
  "workspaces": [
    "apps/*",
    "ui-tui",
    "ui-tui/packages/*",
    "web",
    "tests-js"
  ],
```

`ui-tui/packages/*` 是一个 workspace,所以 `@hermes/ink` 本该由 workspace 解析。
而 `ui-tui/package.json` 又把 `ink-text-input` 的 peer 依赖 `ink` 用 overrides 改写成了
一个**registry 别名** `npm:@hermes/ink@0.0.1`:

`ui-tui/package.json:31 @ 863e313`

```json
  "overrides": {
    "ink-text-input": {
      "ink": "npm:@hermes/ink@0.0.1"
    }
  },
```

脱离根 workspace 时,这个别名会被当成真的 registry 包去解析 —— 于是 404。
**这就是 ◇-R10-ts-1**:项目**知道**这件事,`apps/desktop` 自带一个
`apps/desktop/scripts/assert-root-install.mjs` 专门拦"没从根装"的用法
(见 `apps/desktop/package.json` 的 `dev:renderer` / `build` 脚本都以它开头);
但 `ui-tui` 与 `web` 的 `package.json` **没有**同样的守卫。
*搜索面*:对 `ui-tui/package.json`、`web/package.json`、`ui-tui/packages/hermes-ink/package.json`
三个文件的 `scripts` 段逐个看过,无一条引用 `assert-root-install`;
全仓 `grep -rn assert-root-install --include=*.json --include=*.mjs`(排除 `node_modules`)
只命中 `apps/desktop/` 下的定义与调用。
**这又是一次"守卫装在了哪一层"**:同一个陷阱,三个 workspace 里只有一个装了拦网。

正确装法是从根按 workspace 装,并且**先 build `hermes-ink`**(vitest 需要它的 `dist/`):

```verify
cd /home/user/r10-ts/hermes-agent && npm install --workspace ui-tui --workspace web --no-audit --no-fund
cd /home/user/r10-ts/hermes-agent && npm run build --workspace ui-tui/packages/hermes-ink
```

装出 **466 个 npm 包**。`apps/desktop` 未装:它要 Electron 运行时、e2e 还要 Playwright 浏览器,
体量与网络需求超出本容器的合理范围 —— **按「未执行」如实申报,不假装跑过**(见 §4)。

---

## 2. 真实执行读数

```verify
bash data/r10/probes/ts_test_env.sh run
```

```text
 Test Files  138 passed (138)
      Tests  1530 passed | 1 skipped (1531)
########## vitest: web ##########
 Test Files  27 passed (27)
      Tests  191 passed (191)
```

| 套件 | 测试文件 | passed | failed | skipped |
|---|---|---|---|---|
| `ui-tui`(含 `ui-tui/packages/hermes-ink`) | 138 | 1,530 | **0** | **1** |
| `web` | 27 | 191 | **0** | **0** |
| **合计** | **165** | **1,721** | **0** | **1** |

**零失败。** 这本身是一条值得记的结构性事实:本容器让 6 个 Python 用例必然失败
(无 IPv6 / 以 root 运行 / 无 models.dev 目录 / SQLite 措辞),而 TS 侧 165 个文件一个都没受影响 ——
因为这些套件**不碰网络、不碰真实端口、不碰 SQLite**,它们测的是纯函数与组件渲染。

### 2.1 唯一那条 skipped,逐个点名

按 `CLAUDE.md` 的要求「凡整文件跳过须逐个点名并报出该文件掩盖了多少用例」——
**本次没有整文件跳过**,只有一条单例跳过:

```verify
cd /home/user/r10-ts/hermes-agent/ui-tui && npx vitest run --reporter=json --outputFile=/tmp/ui-tui-vitest.json
```

```text
skipped | ui-tui/packages/hermes-ink/src/utils/execFileNoThrow.test.ts
        | execFileNoThrow with daemon-style children (documented hang)
          without resolveOnExit, await never resolves when daemon inherits stdio
```

**它是被作者有意留下的一条"记录一个已知挂死"的用例**:用例名里自己写着
`(documented hang)`,内容是"不传 `resolveOnExit` 时,子进程继承 stdio 的守护型子进程
会让 await 永不 resolve"。**跳过它是对的** —— 跑它会挂住整个套件。
它掩盖的用例数是 **1**(不是整文件:该文件其余用例正常执行)。

*为什么要专门查这一条*:上一轮(R9D)在 Python 侧栽过 —— 运行器把 "skipped" 缩写成 `s`,
`(1s, 1.1s)` 里的 `1s` 是「1 个跳过」不是「1 秒」,当时被误读成"无整文件跳过"。
本轮用 `--reporter=json` 把每条用例的 status 取出来判定,不靠读摘要行。

---

## 3. 两个口径必须分开报:静态清点 ≠ 运行时计数

```verify
cd /home/user/hermes-agent && for d in ui-tui web; do \
  nf=$(find $d \( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \) | wc -l); \
  cases=$(find $d \( -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \) -print0 \
    | xargs -0 grep -hoE "^[[:space:]]*(it|test)(\.[a-z]+)?\(" | wc -l); \
  printf "%-8s 静态: files=%s cases=%s\n" "$d" "$nf" "$cases"; done
```

```text
ui-tui   静态: files=138 cases=1468
web      静态: files=27 cases=189
```

| 指标 | 静态清点(数 `it(`/`test(` 字面量) | 运行时(vitest 计数) | 差 |
|---|---|---|---|
| `ui-tui` 测试文件 | 138 | 138 | 0 |
| `ui-tui` 用例 | **1,468** | **1,531** | **+63** |
| `web` 测试文件 | 27 | 27 | 0 |
| `web` 用例 | **189** | **191** | **+2** |

**文件数两法一致,用例数不一致 —— 这两个数不能互相代替。**
差额的来源是**运行时才展开的用例**:`it.each([...])` / 循环里生成的 `it(` /
从数据表驱动出来的用例,静态数字面量只会数到 1 次(或 0 次)。

**所以"静态清点"能回答的问题只有一个**:这个目录里有多少测试文件、多少条**写死的**用例。
它**不能**回答"这个套件有多少用例"。上一轮对 `apps/desktop` 的 4,390 这个数,
按本节的结论应当读作**下界**,不是用例数。

---

## 4. 未执行部分,如实申报

| 未跑的 | 规模 | 原因 | 后果 |
|---|---|---|---|
| `apps/desktop` 的 vitest 套件 | 490 个测试文件(静态用例 ≥4,390) | 需要 Electron 运行时;`npm install --workspace apps/desktop` 会拉 `electron@40.10.2` 等重型二进制 | 本轮 H 片(`apps/desktop/electron/`)的行为规格**只有静态阅读,没有执行验证** |
| `apps/desktop` 的 Playwright e2e | 19 个 `.spec.ts`(台账里是 L2/R10,3,250 行) | 还要额外下载浏览器 | 同上 |
| `tests-js` workspace | 未清点 | 不在 R10 范围(台账 round 非 R10) | 无 |

**这一条不打折扣地说清楚**:R10 范围内 `apps/desktop` 是**行数最大的一块**,
而它的测试**一条都没跑过**。H 片的结论全部建立在静态阅读上。
若 R10B 要接着做渲染层,**建议先解决 Electron 依赖**,否则整个桌面端都缺执行验证。

---

## 5. 基线洁净与资源账

```verify
git -C /home/user/hermes-agent status --porcelain && git -C /home/user/hermes-agent diff HEAD --stat
```

两条命令**均输出为空**:基线工作区干净,且**已跟踪文件逐字未变**。
`git archive` 是只读导出,npm 只在 `/home/user/r10-ts/hermes-agent` 里写。

**资源账(与 Python venv 分开记)**:

| 资源 | 开工 | 收工 | 期间安装 |
|---|---|---|---|
| Python 共享 venv | 87 包 | 见本轮报告 §7 | **0** |
| node 副本(`/home/user/r10-ts/hermes-agent`) | 0 | **466 包** | 466,来源 npmjs.org,触发场景 = 本节 §1 的 `npm install --workspace ui-tui --workspace web` |

**node 的 466 个包不进 Python venv 的计数**,两者是不同资源;但按"任何安装都要记来源、
包名与触发场景"的要求,这里明确记下:它由**主线**在**派发子代理之前与之外**执行,
派工书里明写子代理不得跑 npm,十个子代理均自报 `installed_any_package: false`(见本轮报告 §7)。
