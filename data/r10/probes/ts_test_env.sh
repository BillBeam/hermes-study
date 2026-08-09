#!/usr/bin/env bash
# R10:在**基线之外**的副本里装 node 依赖并跑 TS 测试。
#
# 为什么要复制而不是就地跑:基线 /home/user/hermes-agent 是全项目
# `路径:行号 @ 863e313` 引用的基准,必须保持洁净。R8A 有过一次教训 ——
# 子代理在基线里跑 npm,npm 重解析依赖改写了 package-lock.json,
# 恰好被行数复核撞见;若被改文件行数不变就会静默通过,而此后所有引用全部失效。
# 所以这里**先复制整棵树、后安装**,基线上一个字节都不动。
#
# 为什么必须复制**整棵树**而不是单独复制 ui-tui / web(R10 实测踩过):
# 仓库根 package.json 声明了 npm workspaces —— `apps/*`、`ui-tui`、
# `ui-tui/packages/*`、`web`、`tests-js`。于是:
#   · ui-tui 依赖 `"@hermes/ink": "file:./packages/hermes-ink"`,而 ui-tui/package.json
#     又用 overrides 把 ink-text-input 的 peer `ink` 改写成 `npm:@hermes/ink@0.0.1`;
#   · 脱离根 workspace 单独 `npm install ui-tui` 时,这个别名会被当成**registry 包**去解析,
#     得到 `E404 GET https://registry.npmjs.org/@hermes%2fink`。
#     报错点名的是 @hermes/ink,真正的原因是「没有从根安装」。
#   · apps/desktop 自己就带一个 scripts/assert-root-install.mjs 来拦这种用法。
# apps/desktop 的测试不在此脚本内:它要 Electron 运行时(e2e 还要 Playwright 浏览器),
# 体量与网络需求远超本容器的合理范围 —— 那部分按「未执行」如实申报,不假装跑过。
#
# 用法:bash data/r10/probes/ts_test_env.sh setup   # 复制整树 + 按 workspace 安装
#       bash data/r10/probes/ts_test_env.sh run     # 跑 vitest(ui-tui / web)
set -uo pipefail

BASE=${HERMES_BASELINE:-/home/user/hermes-agent}
WORK=${R10_TS_WORK:-/home/user/r10-ts}
TREE="$WORK/hermes-agent"

setup() {
  mkdir -p "$WORK"
  rm -rf "$TREE"
  mkdir -p "$TREE"
  # 用 `git archive` 而不是 cp/rsync 导出副本,有三个好处:
  #   1. 只导出**已跟踪**文件,天然不带 .git 与 node_modules;
  #   2. 导出的内容就是 863e313 这个 commit 本身,副本与引用基准逐字一致;
  #   3. 它是只读操作,基线一个字节都不碰。
  # (本容器没有 rsync,`rsync: command not found` —— 不要改回去。)
  git -C "$BASE" archive --format=tar HEAD | tar -x -C "$TREE"
  echo "== baseline untouched check (须为空) =="
  git -C "$BASE" status --porcelain | head
  echo "== npm install --workspace ui-tui --workspace web (从根) =="
  ( cd "$TREE" && npm install --workspace ui-tui --workspace web \
      --no-audit --no-fund 2>&1 | tail -8 )
  echo "== build hermes-ink(ui-tui 的工作区依赖,vitest 前必须先产出 dist/) =="
  ( cd "$TREE" && npm run build --workspace ui-tui/packages/hermes-ink 2>&1 | tail -8 )
  echo "== baseline untouched check again (须为空) =="
  git -C "$BASE" status --porcelain | head
}

run() {
  for d in ui-tui web; do
    echo "########## vitest: $d ##########"
    # reporter=dot:vitest 4 已删掉 `basic`(用它会得到
    # `Failed to load custom Reporter from basic` 这种看起来像项目坏了的启动错)。
    ( cd "$TREE/$d" && npx vitest run --reporter=dot 2>&1 | tail -45 )
  done
}

case "${1:-}" in
  setup) setup ;;
  run) run ;;
  *) echo "usage: $0 {setup|run}" >&2; exit 2 ;;
esac
