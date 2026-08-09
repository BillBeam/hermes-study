# r11a 片A · 装机与发布 —— 安装器 / 发布流水线 / Nix 打包(L2 结构级理解)

> 底稿,证据层。基线 `NousResearch/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`),只读。
> 溯源约定:凡对基线行为的断言,前面单独一行给 `路径:行号 @ 863e313`,紧跟代码原文块。
>
> **本片的引用保护面(先说清楚,后面不再重复)**:项目的引用校验器
> `scripts/verify_citations.py` 只认白名单扩展名与一份无扩展名文件名单。实测:
> `scripts/hermes-gateway:N`(无扩展名但在名单里、且路径含 `/`)**会被机械校验**;
> `scripts/install.ps1:N` 与 `scripts/install.cmd:N` **完全不被识别为引用**(`citations=0`)。
> 所以本片凡涉及 `.ps1` / `.cmd` 的锚点,读者要用、但**它们没有机器兜底**;
> 关键断言我尽量落在 `.sh` / `.py` / `.nix` / `scripts/hermes-gateway` 上。

---

## 0. 片清单与规模

```verify
awk -F'\t' 'NR>1{n++; l+=$2} END{printf "%d 文件 / %d 行\n", n, l}' data/r11a/slices/slice-L2-A.tsv
```

```text
32 文件 / 21851 行
```

分三块:

```verify
awk -F'\t' 'NR>1{if($1 ~ /^scripts\/install/){a+=$2; an++} else if($1 ~ /^scripts\/(release|build_|generate_)/){b+=$2; bn++} else {c+=$2; cn++}} END{printf "安装器 %d 文件/%d 行 | 发布与产物 %d 文件/%d 行 | Nix与容器 %d 文件/%d 行\n", an, a, bn, b, cn, c}' data/r11a/slices/slice-L2-A.tsv
```

```text
安装器 4 文件/7762 行 | 发布与产物 4 文件/3480 行 | Nix与容器 24 文件/10609 行
```

逐文件角色(**每个文件一句话,全路径**):

**(一)安装器本体 —— 4 个文件 / 7,762 行**

| 全路径 | 行 | 角色 |
|---|---|---|
| `scripts/install.sh` | 3,370 | POSIX 安装器(Linux / macOS / Android-Termux),`curl \| bash` 一行命令的落点;四种入口模式,见 §2.1 |
| `scripts/install.ps1` | 4,262 | Windows 安装器,`irm \| iex` 的落点;与上者**不等价**,差异见 §3 |
| `scripts/install.cmd` | 28 | CMD 用户的薄外壳(28 行里只有 1 行是动作):`powershell -ExecutionPolicy ByPass -NoProfile -Command "iex (irm .../install.ps1)"`;非 0 退出码时 `pause` 留住窗口,免得双击后一闪而过 |
| `scripts/install_psutil_android.py` | 102 | Termux 专用补丁安装器:下载 psutil sdist、把 `sys.platform.startswith('linux')` 改成 `("linux","android")` 再装;上游 PR 合并后即删的临时件 |

**(二)发布与产物生成 —— 4 个文件 / 3,480 行**

| 全路径 | 行 | 角色 |
|---|---|---|
| `scripts/release.py` | 2,637 | 发布工具:CalVer 标签 + SemVer 版本文件 + 变更日志 + `gh release create`;**其中 2,026 行(76.8%)是贡献者邮箱→GitHub 用户名的冻结映射表**,见 §2.9 |
| `scripts/build_skills_index.py` | 459 | 爬 6 个技能源,产出 `website/static/api/skills-index.json`(静态托管,免得运行时打 GitHub API) |
| `scripts/generate_conformance_vectors.py` | 266 | 用四个平台的**原生渲染器当 oracle**,产出 `tests/conformance/vectors/<platform>.json`,给跨仓连接器当可执行规格 |
| `scripts/build_model_catalog.py` | 118 | 把仓内硬编码的 `OPENROUTER_MODELS` / `_PROVIDER_MODELS["nous"]` 导出成 `website/static/api/model-catalog.json` |

**(三)Nix 打包与容器接驳 —— 24 个文件 / 10,609 行**

| 全路径 | 行 | 角色 |
|---|---|---|
| `nix/packages.nix` | 75 | `perSystem.packages` 输出集(9 个)+ `full = minimal.override { extraDependencyGroups = ... }` 的可选组清单 |
| `nix/hermes-agent.nix` | 270 | 主包(可 `.override`):把 venv、skills、plugins、locales、optional-mcps、web_dist、TUI 用 `makeWrapper` 包成 3 个 bin |
| `nix/python.nix` | 157 | uv2nix 虚拟环境构建器;含 aarch64-darwin 的 7 个 nixpkgs 预构建替换,以及 `HERMES_NIX_BUILD=1` 这道"只许封闭派生打 wheel"的闸 |
| `nix/lib.nix` | 351 | 共享库:npm workspace 发现、Python/npm 源过滤器(控制重建范围)、`nodejs_26 + npm 12` 组合、`update-npm-lockfile` 脚本 |
| `nix/checks.nix` | 582 | 17 个构建期检查(3 个三系统 + 14 个仅 Linux),外加 `packages.configKeys` |
| `nix/nixosModules.nix` | 1,008 | `services.hermes-agent` NixOS 模块:23 个顶层选项 + 6 个 `container.*`;两种模式(原生 systemd / OCI 容器) |
| `nix/devShell.nix` | 64 | `devShells.default`:收集各 npm workspace 的 `packageJsonPath`,统一 stamp + `npm i --package-lock-only` + `npm ci` |
| `nix/overlays.nix` | 14 | `flake.overlays.default`:`pkgs.hermes-agent` 是**本 flake 自己那个派生的别名**,不是拿消费者的 nixpkgs 重新实例化 |
| `nix/desktop.nix` | 196 | Electron 桌面派生:renderer npm 构建 + 用 Electron 自己的 headers 从源码编 node-pty + wrapper |
| `nix/sandbox.nix` | 124 | 把 `scripts/dev-sandbox.sh` 包成 `sandbox` 可执行:注入 CA、动态链接器、Node 目录、Electron 运行时库路径、assets 目录 |
| `nix/tui.nix` | 29 | TUI(Ink/React)的 esbuild 构建,产物落 `$out/lib/hermes-tui/dist` |
| `nix/web.nix` | 33 | Web 仪表盘(Vite/React)构建,产物落 `$out`(被主包软链成 `web_dist`) |
| `nix/configMergeScript.nix` | 33 | 生成一个 `python3 + pyyaml` 脚本:把 Nix 生成的 JSON 深合并进已存在的 `config.yaml`,Nix 键覆盖、用户键保留 |
| `nix/node-gyp-11-4-0.nix` | 40 | 从 GitHub tag 建 node-gyp 11.4.0(nixpkgs 里的版本不认 npm12 的新配置变量) |
| `nix/node-gyp-11-4-0-package-lock.json` | 5,246 | **纯数据**:node-gyp 11.4.0 的 npm 锁文件,见 §2.11.3「它为什么在这里、谁读它」 |
| `nix/npm-12-0-2.nix` | 29 | 从 registry tarball 建 npm 12.0.2,再 `symlinkJoin` 到 nodejs_26 上 |
| `scripts/dev-sandbox.sh` | 591 | **安装器自己的测试床**:在 user/mount/pid/net 命名空间里造一个假 Internet(MITM 代理 + git-upload-pack shim),把 `install.sh` 真跑一遍 |
| `scripts/lib/node-bootstrap.sh` | 437 | 可 source 的 Node 引导库(fnm/proto/nvm/pkg/brew/官方 tarball 五级),**运行时**用;`scripts/install.sh` 不 source 它,见 §2.7 |
| `scripts/hermes-gateway` | 416 | 独立网关入口 + systemd/launchd 服务安装器;**全仓无人引用**,且与 CLI 抢同一个 unit 文件,见 §5 ■-1 |
| `scripts/docker_config_migrate.py` | 110 | 容器启动时跑的配置迁移:先备份 `config.yaml`/`.env`,再 `migrate_config`;低于支持下限则整体跳过 |
| `scripts/docker_rebootstrap_nous_session.py` | 227 | 容器启动时的窄口子:当本地 Nous bootstrap 会话被判死,用 `HERMES_AUTH_JSON_REBOOTSTRAP` **只替换** `providers.nous` 一节;纯 stdlib、任何异常都原样退出 0 |
| `scripts/tests/test-install-ps1-longpath.ps1` | 323 | install.ps1 的 8.3 短路径规范化测试,**唯一被 CI 跑到的那个** |
| `scripts/tests/test-install-ps1-stage-protocol.ps1` | 134 | stage 协议元数据面(`-ProtocolVersion` / `-Manifest` / 未知 `-Stage`)冒烟测试,**CI 未接** |
| `scripts/tests/test-install-ps1-gitbash-compatibility.ps1` | 120 | Git Bash 兼容 + Mandatory-ASLR 提示的单测(用 PowerShell AST 抽函数,不执行安装器),**CI 未接** |

---

## 1. 这一片解决什么问题

一句话:**把"一个 Python 单体 + 一个 npm workspace + 一堆可选原生依赖"变成"一条命令就能装到陌生机器上、并且以后还能自己更新"**。

难点不在"跑 pip install",在于:

1. **目标机器什么都没有**。没有合适的 Python、没有 Node、没有 git、没有 ripgrep/ffmpeg;可能是 root、可能是普通用户、可能是手机上的 Termux。安装器要自己把这些补齐,还不能要求 sudo。
2. **同一份产品有四条互不相同的装机路线**:`curl | bash`(POSIX)、`irm | iex`(Windows)、Nix flake、Docker 镜像。它们装出来的东西**不一样**——Node 版本不同、技能种子不同、更新方式不同——而运行时要能分辨自己是被哪条路线装的(`.install_method`,见 §4.1)。
3. **安装器还是别人的库**。桌面 Electron 应用把安装器当成"带结构化进度回报的子进程"来驱动(stage 协议),所以安装器要同时是"给人看的脚本"和"给程序调的 API"。
4. **发布本身是最轻的一环**。`scripts/release.py` 只做标签 + 版本文件 + 变更日志,**不产二进制、不签名、不校验**(§5 负结论-2)——因为"产物"就是 git 仓库本身,安装器 clone 它。

---

## 2. 逐机制

### 2.1 install.sh 的四个入口模式

文件末尾的 dispatch 是理解整个脚本的钥匙:同一个文件有四种完全不同的用法。

`scripts/install.sh:3362-3370 @ 863e313`

```bash
if [ "$MANIFEST_MODE" = true ]; then
    emit_manifest
elif [ -n "$STAGE_NAME" ]; then
    run_stage_protocol "$STAGE_NAME"
elif [ -n "$ENSURE_DEPS" ]; then
    ensure_mode
else
    main
fi
```

| 模式 | 触发 | 干什么 |
|---|---|---|
| 整装 | 默认 | `main()`:探测 → clone → venv → 依赖 → PATH → 配置 → 向导 → 网关 →(可选桌面)→ 打 `.install_method` |
| 清单 | `--manifest` | 打印一行 JSON:`protocol_version` + stage 列表(名字/标题/分类/是否需要用户输入) |
| 单阶段 | `--stage NAME [--json]` | 只跑一个阶段,`--json` 时输出 `{"ok":..,"stage":..,"skipped":..}` 结果帧 |
| 补依赖 | `--ensure node,browser,...` | **不 clone、不建 venv**,只把指定的系统依赖补齐 |

单阶段模式有一个值得抄的细节:阶段体在**子 shell** 里跑。

`scripts/install.sh:3305-3308 @ 863e313`

```bash
    set +e
    ( run_stage_body "$stage" )
    local code=$?
    set -e
```

理由写在紧邻的注释里:阶段助手函数(`clone_repo`、`install_deps`)是为整装流程写的,失败时直接 `exit 1`;不套子 shell 的话,一个失败的 `--stage` 会在**打印结果帧之前**终止进程,驱动方看到的是"没有结果帧",而不是干净的 `{ok:false}`。**这是"脚本兼作 API"必须付的代价之一**。

哪些阶段需要人:

`scripts/install.sh:329-334 @ 863e313`

```bash
stage_needs_user_input() {
    case "$1" in
        setup|gateway) return 0 ;;
        *) return 1 ;;
    esac
}
```

`--non-interactive` 时这两个阶段直接跳过并回报 `skipped:true`——**不是失败,是契约里的一个合法结局**。

### 2.2 布局决策:代码装到哪、命令链到哪

`resolve_install_layout()` 按三条规则定 `INSTALL_DIR`,`get_command_link_dir()` 定命令软链目录。默认分支:

`scripts/install.sh:446-447 @ 863e313`

```bash
    # Default: non-root, non-Termux → legacy user-scoped layout.
    INSTALL_DIR="$HERMES_HOME/hermes-agent"
```

全表:

| 情形 | 代码目录 | 命令目录 |
|---|---|---|
| 显式 `--dir` 或 `$HERMES_INSTALL_DIR` | 用户给的 | 按下面三条 |
| Termux(任何 uid) | `$HERMES_HOME/hermes-agent` | `$PREFIX/bin` |
| Linux + root + **无**遗留安装 | `/usr/local/lib/hermes-agent` | `/usr/local/bin` |
| Linux + root + 有 `$HERMES_HOME/hermes-agent/.git` | 保留遗留布局 | `$HOME/.local/bin` |
| 其他(非 root / macOS root) | `$HERMES_HOME/hermes-agent` | `$HOME/.local/bin` |

两个设计取舍值得记:

**macOS 的 root 安装故意不走 FHS**。

`scripts/install.sh:420-421 @ 863e313`

```bash
    # macOS root installs keep the legacy layout because /usr/local/ on macOS
    # is Homebrew territory and we don't want to fight that.
```

**root FHS 布局会顺手改 uv 的 Python 安装目录**,因为 uv 默认落 `/root/.local/share/uv`,非 root 用户连遍历都进不去——于是共享的 `/usr/local/bin/hermes` 会拿到一个"解释器不可执行"的 venv(#21457)。**这是"系统级安装"这件事真正的难点:不是路径,是可读性**。

`scripts/install.sh:436-437 @ 863e313`

```bash
        export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-/usr/local/share/uv/python}"
        export UV_PYTHON_BIN_DIR="${UV_PYTHON_BIN_DIR:-/usr/local/share/uv/bin}"
```

命令本身**不是软链,是生成的 shim**。`setup_path()` 写三个包装脚本(`hermes`、`hermes-agent`、`hermes-acp`),每个都先 `unset PYTHONPATH` / `unset PYTHONHOME` 再 `exec` venv 解释器。为什么不用 uv 生成的 console script:那些脚本靠 `realpath` 定位自己,而**原版 macOS 没有 `realpath`**(`scripts/install.sh:1737-1740`)。为什么写之前先 `rm -f`:

`scripts/install.sh:1732-1735 @ 863e313`

```bash
    # Older installs created this path as a symlink to $HERMES_BIN. Without
    # the rm, `cat >` follows the symlink and overwrites the venv pip entry
    # point with this shim — making `exec "$HERMES_BIN"` self-recurse. (#21454)
    rm -f "$command_link_dir/hermes"
```

### 2.3 依赖获取的五条链,与各自的校验姿态

这是本片最值得穷举的一处:安装器一共从五个地方取东西,**只有一条链是哈希校验的**。

| # | 取什么 | 从哪 | 怎么校验 |
|---|---|---|---|
| 1 | uv 二进制 | `https://astral.sh/uv/install.sh` 下载后 `sh` 执行 | **仅 TLS**,无校验和/签名 |
| 2 | Node.js | 抓 `https://nodejs.org/dist/latest-v22.x/` 目录页正则出 tarball 名再下 | **仅 TLS**;同目录的 `SHASUMS256.txt` 未取用 |
| 3 | 仓库源码 | `git clone --depth 1`,先 SSH 后 HTTPS | 无提交签名验证 |
| 4 | Python 依赖 | `uv sync --extra all --locked`(Tier 0) | **`uv.lock` 里每个传递依赖的 SHA256**,不符即拒 |
| 5 | npm 全局包 | `npm install -g agent-browser@^0.26.0` 等 | registry 的 `integrity`;但版本是 caret 范围,不钉死 |

第 4 条的理由,作者自己写得比我清楚:

`scripts/install.sh:1546-1552 @ 863e313`

```bash
    # Hash-verified install (Tier 0) — when uv.lock is present, prefer
    # `uv sync --locked`. The lockfile records SHA256 hashes for every
    # transitive, so a compromised transitive (different hash than what
    # we shipped) is REJECTED by the resolver. This is the *only* path
    # that protects against the "direct dep is fine, but the dep's dep
    # got worm-poisoned overnight" failure mode. All `uv pip install`
    # tiers below re-resolve transitives fresh from PyPI without any
```

Tier 0 之后有一个**三级降级梯**,任何一级成功就停:

`scripts/install.sh:1673-1675 @ 863e313`

```bash
    install_tier "all" ".[all]" \
        || install_tier "all minus known-broken (${_BROKEN_EXTRAS[*]:-none})" "$_SAFE_SPEC" \
        || install_tier "core only (no extras)" "."
```

`_SAFE_SPEC` 不是硬编码的:脚本用内嵌 Python 读 `pyproject.toml` 的 `[project.optional-dependencies].all`,解析出所有 `hermes-agent[<extra>]`,再减去 `_BROKEN_EXTRAS`。基线里这个列表是空的,所以第二级现在等价于第一级——**它是留给"某个 extra 突然装不上"时改一行就能救急的位置**。

`scripts/install.sh:1610 @ 863e313`

```bash
    local _BROKEN_EXTRAS=()  # populate when an extra becomes unresolvable
```

Tier 0 的关键旗标选择也记在注释里:用 `--extra all` 而**不是** `--all-extras`,因为后者会绕开 `[all]` 这个人工策展的集合,把 `[matrix]`(Windows 上要 python-olm + make)和 `[rl]`(git+https 依赖,离线必挂)一起拉进来。

`scripts/install.sh:1577-1578 @ 863e313`

```bash
        #   --extra all  = install just the `[all]` extra's contents.
        #                  This respects the curation in pyproject.toml.
```

npm 侧则是**时间盒 + `--ignore-scripts`**:

`scripts/install.sh:2680-2683 @ 863e313`

```bash
    if ! run_with_timeout "$NODE_DEPS_TIMEOUT" "$npm_bin" install -g --prefix "$HERMES_HOME/node" --silent --ignore-scripts \
        "agent-browser@^0.26.0" \
        "@askjo/camofox-browser@^1.5.2" \
        >"$log_file" 2>&1; then
```

### 2.4 失败与回滚

安装器**没有事务**,但有若干条"永不删用户东西"的规矩,值得单列:

**(a) 半途中断的 clone 不删,挪走**(#40998)。

`scripts/install.sh:1236-1237 @ 863e313`

```bash
    if [ -d "$INSTALL_DIR/.git" ] && ! git -C "$INSTALL_DIR" rev-parse --verify HEAD >/dev/null 2>&1; then
        backup_dir="${INSTALL_DIR}.broken-$(date -u +%Y%m%d-%H%M%S)"
```

**(b) 上一次冲突残留的未合并索引先 `git reset -q` 清掉**,否则 `git stash` 会以 "could not write index" 中止,整个 repository 阶段失败(#4735)。

`scripts/install.sh:1260-1263 @ 863e313`

```bash
                if [ -n "$(git ls-files --unmerged)" ]; then
                    log_info "Clearing unmerged index entries from a previous conflict..."
                    git reset -q
                fi
```

**(c) 更新前自动 stash,冲突时把工作树复位但保留 stash**。

`scripts/install.sh:1330-1334 @ 863e313`

```bash
                        log_info "Your stashed changes are preserved — nothing is lost."
                        log_info "  Stash ref: $autostash_ref"
                        git reset --hard HEAD >/dev/null 2>&1 || true
                        log_info "Working tree reset to clean state."
                        log_info "Restore your changes later with: git stash apply $autostash_ref"
```

**(d) `--commit` 永不把已有安装往回滚**:目标提交若是 HEAD 的祖先就忽略,除非 `--force-commit`。理由是引导安装器把构建期的 `BUILD_PIN_COMMIT` 烤进二进制、每次都当 `--commit` 传,几个月前构建的安装器否则会把当前 checkout 倒回去。

`scripts/install.sh:1381-1383 @ 863e313`

```bash
        if git rev-parse --verify --quiet HEAD >/dev/null 2>&1 \
           && git merge-base --is-ancestor "$INSTALL_COMMIT" HEAD 2>/dev/null \
           && [ "$(git rev-parse "$INSTALL_COMMIT^{commit}" 2>/dev/null)" != "$(git rev-parse HEAD)" ]; then
```

**(e) npm 锁文件的脏改动直接丢弃**,避免 `npm ci` 顺手改的 lockfile 卡住下一次更新。

`scripts/install.sh:267-268 @ 863e313`

```bash
discard_update_lockfile_churn() {
    local repo="${1:-$INSTALL_DIR}"
```

**(f) `.hermes-bootstrap-complete` 原子发布**:先写 `.tmp` 再 `mv -f`。

`scripts/install.sh:2567-2568 @ 863e313`

```bash
    # Atomic publish: the macOS launcher predicate only checks existence, so a
    # torn write would arm the fast path against a half-written marker.
```

### 2.5 stage 协议:与 Windows 的"镜像"到底镜到什么程度

`scripts/install.sh:3180-3181 @ 863e313`

```bash
# Desktop bootstrap stage protocol. Mirrors the Windows install.ps1 surface
# closely enough for the Electron bootstrap runner to show structured progress.
```

"closely enough" 这四个字很诚实——**两边的阶段名交集只有 6 个**:

```verify
cd /home/user/hermes-agent && SH=$(grep -oE '"name":"[a-z-]+"' scripts/install.sh | sed 's/.*:"//; s/"//' | sort -u) && PS=$(grep -oE '@\{ Name = "[a-z-]+".*Worker = "Stage-[A-Za-z]+" \}' scripts/install.ps1 | sed 's/@{ Name = "\([a-z-]*\)".*/\1/' | sort -u) && echo "sh=$(echo "$SH" | wc -l) ps1=$(echo "$PS" | wc -l) common=$(comm -12 <(echo "$SH") <(echo "$PS") | wc -l)" && echo "common: $(comm -12 <(echo "$SH") <(echo "$PS") | tr '\n' ' ')" && echo "sh-only: $(comm -23 <(echo "$SH") <(echo "$PS") | tr '\n' ' ')" && echo "ps1-only: $(comm -13 <(echo "$SH") <(echo "$PS") | tr '\n' ' ')"
```

```text
sh=11 ps1=16 common=6
common: desktop gateway node-deps path repository venv 
sh-only: complete config prerequisites python-deps setup 
ps1-only: bootstrap-marker config-templates configure dependencies git node platform-sdks python system-packages uv 
```

**协议本身兼容,阶段名不兼容**。两边都声明 `protocol_version = 1`(POSIX 侧在 `emit_manifest` 的 JSON 字面量里;Windows 侧是 `scripts/install.ps1:396` 的 `$InstallStageProtocolVersion = 1`),但驱动方只能"动态迭代 manifest",不能对阶段名做任何假设——这一点 `scripts/install.ps1:3934` 的注释也明说了(加阶段是**加性**的,不许 bump 协议版本)。POSIX 侧把 Windows 的 uv/python/git/node/system-packages 五个阶段合成了一个 `prerequisites`,把 dependencies 叫 `python-deps`,又多了一个 Windows 没有的 `complete`(它负责写 `.install_method`,§4.1)。

驱动方的写法印证了这一点(片外驱动)。

`apps/desktop/electron/bootstrap-runner.ts:771-779 @ 863e313`

```ts
  const args = isPosix
    ? [
        '--stage',
        stage.name,
        '--non-interactive',
        '--json',
        ...buildPosixPinArgs({ installStamp, activeRoot, hermesHome, pinCommit })
      ]
    : ['-Stage', stage.name, '-NonInteractive', '-Json', ...buildPinArgs(installStamp, { pinCommit })]
```

**是按平台分叉的两套调用,不是一套**。

### 2.6 install.ps1 的 Windows 特有难题(结构级)

`install.ps1` 比 `install.sh` 多出来的 892 行,绝大部分不是功能,是**Windows 的坑**:

- **8.3 短路径**(`scripts/install.ps1:107-350`)。用户名带空格/点/重音时,Windows 会把 `%TEMP%`、`%LOCALAPPDATA%`、`%USERPROFILE%` 暴露成 `C:\Users\FIRST~1.LAS\...`;PowerShell 的 FileSystem provider 一碰这种路径就抛"路径不存在"(还会本地化)。脚本在**最开头**就把这些环境变量展开成长路径。测试见 `scripts/tests/test-install-ps1-longpath.ps1`。
- **进度条**(`scripts/install.ps1:86`)。Windows PowerShell 5.1 的进度 UI 每收一个字节就同步重绘,把下载拖慢 10-100 倍(57MB 的 PortableGit:开进度条 5 分钟 vs 关掉 20 秒)。`$ProgressPreference = "SilentlyContinue"`。
- **必须同时能在 PS 5.1 和 pwsh 7 下解析**——因为 `irm | iex` 落进用户已有的那个 shell,而 5.1 是 Windows 自带的。CI 因此对 longpath 测试跑**两遍**(该工作流文件属 B 片):

`.github/workflows/installer-tests.yml:32-34 @ 863e313`

```yaml
      - name: 8.3 short-path normalization (pwsh 7)
        shell: pwsh
        run: pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test-install-ps1-longpath.ps1
```

- **没有 git 时的 ZIP 兜底**(`scripts/install.ps1:2060-2135`)。下 `https://github.com/NousResearch/hermes-agent/archive/<ref>.zip` 解压,然后 `git init` + `remote add` + `fetch --depth 1` + `checkout -f`,把它变成一个有 HEAD 的真 checkout。**`install.sh` 没有这条兜底**——POSIX 侧 git 是硬前提。
- **PortableGit / 便携 Node 全部装进 `$HermesHome`**,不走需要 UAC 的 MSI。winget 只作降级路径。32 位/32 位 ARM 的 Windows 拿不到 PortableGit,退到 MinGit 32-bit 并明确警告"依赖 bash 的功能(终端工具、agent-browser)在这台机器上不可用"(`scripts/install.ps1:1247-1267`)。

### 2.7 node-bootstrap.sh:第二套 Node 策略,而且 install.sh 不用它

`scripts/lib/node-bootstrap.sh` 是一个**可 source 的库**,五级策略(PATH 上的现成 node → `~/.hermes/node/` → fnm/proto/nvm → Termux pkg / brew → 官方 tarball)。它的输入面写在文件头:

`scripts/lib/node-bootstrap.sh:26-28 @ 863e313`

```bash
HERMES_NODE_MIN_VERSION="${HERMES_NODE_MIN_VERSION:-20}"
HERMES_NODE_TARGET_MAJOR="${HERMES_NODE_TARGET_MAJOR:-22}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
```

谁 source 它?**运行时**:`hermes_constants.py:322` 把它记成 `_NODE_BOOTSTRAP_SCRIPT`,CLI 在缺 node/npm 时 source 它。

`hermes_cli/main.py:1827 @ 863e313`

```python
    helper = PROJECT_ROOT / "scripts" / "lib" / "node-bootstrap.sh"
```


谁**不** source 它?安装器自己。

```verify
cd /home/user/hermes-agent && printf 'scripts/install.sh 里 node-bootstrap = %s 处\n' "$(grep -c 'node-bootstrap' scripts/install.sh)"
```

```text
scripts/install.sh 里 node-bootstrap = 0 处
```

于是同一件事(装 Node)有两份独立实现:`install.sh` 的 `check_node`/`install_node`(`:820-975`)与 `node-bootstrap.sh` 的 `ensure_node`(`:393`)。两者的**接受门槛不同**(`node_satisfies_build` 要 ≥22.22,`HERMES_NODE_MIN_VERSION` 默认 20),**策略也不同**(`install.sh` 完全没有 fnm/proto/nvm 分支)。`node-bootstrap.sh:50-57` 的 `_nb_get_link_dir` 注释直接写着 "Mirrors get_command_link_dir() from install.sh"——**两份代码互为镜像、靠注释维持同步**,这是典型的"复制粘贴型契约"。

### 2.8 install_psutil_android.py

一个自认的临时件:psutil 的 setup 把 Linux 源码路径挡在 `sys.platform.startswith('linux')` 后面,而 Termux 上 Python 报 `sys.platform == 'android'`,于是 `pip install psutil` 直接拒绝——尽管复用 Linux 源码路径能编过。脚本下载官方 sdist、打一行补丁(`LINUX = sys.platform.startswith(("linux", "android"))`)、`pip install --no-build-isolation` 装上。真正的补丁逻辑不在这个脚本里,而在 `hermes_cli/psutil_android.py`(片外),脚本只是 CLI 外壳:`--pip "<cmd>"` / `--uv`,都不给时自动探测 `uv`,再退回 `<sys.executable> -m pip`。

### 2.9 release.py:CalVer 标签 + SemVer 版本,两套号

`scripts/release.py` 一共只有 5 个命令行参数(`--bump {major,minor,patch}` / `--publish` / `--date` / `--first-release` / `--output`),没有子命令。它的**步骤面**是固定的一条线:

| # | 步骤 | 锚点 |
|---|---|---|
| 1 | 定 CalVer 日期(`--date` 或今天),拼 `v{Y}.{M}.{D}` | `scripts/release.py:2490-2497` |
| 2 | 同日重复发布则加 `.2`/`.3` 后缀 | `scripts/release.py:2140-2149` |
| 3 | 读 `hermes_cli/__init__.py` 的 `__version__`,按 `--bump` 升 SemVer | `scripts/release.py:2152-2178` |
| 4 | 取上一个 `v20*` 标签,收集其后的提交 | `scripts/release.py:2132-2137` |
| 5 | 提交按 conventional-commit 前缀归 8 类,解析 co-author,邮箱→`@用户名` | `scripts/release.py:2244-2311` |
| 6 | 生成变更日志(`--output` 写文件,否则打印) | `scripts/release.py:2372` |
| 7 | **仅 `--publish`**:改三个版本文件 → `git add` + `git commit` | `scripts/release.py:2554-2572` |
| 8 | `git tag -a` → `git push origin HEAD --tags` | `scripts/release.py:2574-2591` |
| 9 | `gh release create --notes-file .release_notes.md` | `scripts/release.py:2593-2601` |

第 1、2 步:

`scripts/release.py:2497-2498 @ 863e313`

```python
    base_tag = f"v{calver_date}"
    tag_name, calver_date = next_available_tag(base_tag)
```

第 7 步改的三个文件:`hermes_cli/__init__.py` 的 `__version__` 与 `__release_date__`、`pyproject.toml` 的 `version`、`apps/desktop/package.json` 的 `version`。第三个是"桌面 About 面板读运行时版本,但 `app.getVersion()` 和打包元数据仍读这个字段"。

`scripts/release.py:2181-2183 @ 863e313`

```python
def update_version_files(semver: str, calver_date: str):
    """Update version strings in source files."""
    # Update __init__.py
```

**降级路径全是"留在本地、告诉你手动怎么办"**:push 失败打印 `git push origin HEAD --tags`;`gh` 不存在或失败就保留 `.release_notes.md` 并打印完整的 `gh release create` 命令。整个脚本没有回滚——标签已经打上了。

`scripts/release.py:2618-2619 @ 863e313`

```python
            if result is None:
                print("  ✗ GitHub release skipped: `gh` CLI not found.")
```

**邮箱映射表是这个文件最大的组成部分**:

```verify
cd /home/user/hermes-agent && python3 -c "
src=open('scripts/release.py',encoding='utf-8').read().splitlines()
start=next(i for i,l in enumerate(src,1) if l.startswith('LEGACY_AUTHOR_MAP = {'))
end=next(i for i,l in enumerate(src,1) if i>start and l.rstrip()=='}')
print('LEGACY_AUTHOR_MAP %d-%d = %d 行 / 文件 %d 行 = %.1f%%' % (start, end, end-start+1, len(src), 100*(end-start+1)/len(src)))
"
```

```text
LEGACY_AUTHOR_MAP 46-2071 = 2026 行 / 文件 2637 行 = 76.8%
```

`LEGACY_AUTHOR_MAP` 被显式冻结,新条目改走 `contributors/emails/` 一文件一条目的目录,目录优先。**理由是合并冲突**:一个 2,000 行的字典,每个 PR 都往里加一行,必冲突;一文件一条目按构造不冲突。

`scripts/release.py:2106 @ 863e313`

```python
AUTHOR_MAP = {**LEGACY_AUTHOR_MAP, **_load_contributor_dir()}
```

### 2.10 三个产物生成脚本

三者形状一致:**读仓内权威 → 写一个 JSON → 由别的东西消费**,并且都自称"不是真相源"。

| 脚本 | 权威来源 | 产物 | 消费者 |
|---|---|---|---|
| `scripts/build_model_catalog.py` | `hermes_cli/models.py` 的 `OPENROUTER_MODELS` / `_PROVIDER_MODELS["nous"]` | `website/static/api/model-catalog.json` | 运行时 fetch;取不到就回落同一份仓内硬编码表 |
| `scripts/build_skills_index.py` | 6 个技能源(skills.sh / GitHub taps / official / clawhub / lobehub / browse.sh)的**网络爬取** | `website/static/api/skills-index.json` | `hermes skills search/install`,免得打 GitHub API |
| `scripts/generate_conformance_vectors.py` | 四个平台适配器的 `format_message`(telegram / slack / whatsapp / discord) | `tests/conformance/vectors/<platform>.json` | 跨仓 gateway-gateway 连接器的 vitest |

`build_model_catalog.py` 有一个回归测试钉住"产物与提交进仓的文件一致"(`tests/hermes_cli/test_model_catalog.py:459-486`),`generate_conformance_vectors.py` 同理(`tests/conformance/test_vector_generator.py:94`)。`build_skills_index.py` 因为要联网,改为**健康闸**:失败时**绝不写** `OUTPUT_PATH`,宁可让站点继续用旧索引。

`scripts/build_skills_index.py:432-433 @ 863e313`

```python
        # IMPORTANT: do NOT write OUTPUT_PATH on failure. The index file is
        # gitignored, so a fresh deploy checkout has no copy on disk — leaving
```

`generate_conformance_vectors.py` 有个值得抄的设计:每条向量带一个 `expect` 字段,取值 `parity` / `semantic` / `divergent`——**把"两边故意不一样"也编码进规格**,而不是让测试作者去猜哪些差异是 bug。产物里还烤进 oracle 的 commit,所以下游能看出自己对的是哪一版渲染器。

`scripts/generate_conformance_vectors.py:21-23 @ 863e313`

```python
Expect semantics (consumed by the gg runner):
  parity    connector render must BYTE-EQUAL native_output
            (Slack / WhatsApp — same-dialect ports; most Discord).
```

### 2.11 Nix:另一条完整的装机路线

#### 2.11.1 分层

`flake.nix` 只做一件事:声明三个 system,再 import 五个文件。

`flake.nix:40-46 @ 863e313`

```nix
      imports = [
        ./nix/packages.nix
        ./nix/overlays.nix
        ./nix/nixosModules.nix
        ./nix/checks.nix
        ./nix/devShell.nix
      ];
```

`nix/packages.nix` 是输出集:

`nix/packages.nix:50-57 @ 863e313`

```nix
      packages = {
        node-gyp =
          (pkgs.callPackage ./lib.nix {
            inherit (pkgs) npm-lockfile-fix;
          }).node-gyp;
        default = full;

        inherit sandbox;
```

`default = full`,而 `full` 是 `minimal` 加 18 个可选依赖组的 override;matrix 只在 Linux 加,因为 oqs/liboqs 没有 aarch64-darwin wheel(`nix/packages.nix:45-46`)。

`nix/packages.nix:23-26 @ 863e313`

```nix
      # All platform-portable optional integrations pre-built.
      full = minimal.override {
        extraDependencyGroups = [
          "anthropic"
```

#### 2.11.2 主包做的事:把"运行时环境"固化成 wrapper 里的环境变量

`nix/hermes-agent.nix:186-195 @ 863e313`

```nix
        makeWrapper ${hermesVenv}/bin/${name} $out/bin/${name} \
          --suffix PATH : "${runtimePath}" \
          --set HERMES_BUNDLED_SKILLS $out/share/hermes-agent/skills \
          --set HERMES_OPTIONAL_SKILLS $out/share/hermes-agent/optional-skills \
          --set HERMES_BUNDLED_PLUGINS $out/share/hermes-agent/plugins \
          --set HERMES_BUNDLED_LOCALES $out/share/hermes-agent/locales \
          --set HERMES_OPTIONAL_MCPS $out/share/hermes-agent/optional-mcps \
          --set HERMES_WEB_DIST $out/share/hermes-agent/web_dist \
          --set HERMES_TUI_DIR $out/ui-tui \
          --set HERMES_PYTHON ${hermesVenv}/bin/python3 \
```

对照 §2.2:`install.sh` 的 shim 靠 `unset PYTHONPATH` + 绝对路径解释器,Nix 靠 `makeWrapper --set`。**同一个问题(让二进制找到自己的资产)的两种解法**,而运行时代码只需要认这几个环境变量——这就是"打包方式可替换"的接口。

注意 `--suffix PATH`(不是 `--prefix`),原因写在 NixOS 模块的头注释里——容器模式下用户 apt/uv 装的版本要能盖过 store 里的。

`nix/nixosModules.nix:12-13 @ 863e313`

```nix
#
# Tool resolution: the hermes wrapper uses --suffix PATH for nix store tools,
```

一个**血泪注释**值得单摘:`--set HERMES_NODE ${...}` 后面那个表达式把行续符**折进了插值内部**。

`nix/hermes-agent.nix:197-202 @ 863e313`

```nix
            # Fold the line continuation INTO the optionalString: a bare
            # `\` on the line above an empty expansion would dangle onto a
            # blank line, ending the makeWrapper command early and running
            # the next flag as its own shell command (`--suffix: command
            # not found`). Only reproduces when rev == null (dirty trees).
            lib.optionalString (rev != null) " \\\n          --set HERMES_REVISION ${rev}"
```

#### 2.11.3 `nix/node-gyp-11-4-0-package-lock.json` 为什么在这里、谁读它

**它是数据,不是代码**:node-gyp 11.4.0 自己的 npm 锁文件,lockfileVersion 3,367 个包条目。

```verify
cd /home/user/hermes-agent && python3 -c "
import json
d=json.load(open('nix/node-gyp-11-4-0-package-lock.json'))
print('name=%s version=%s lockfileVersion=%s packages=%d' % (d['name'], d['version'], d['lockfileVersion'], len(d['packages'])))
" && printf '仓库内引用它的文件: %s\n' "$(grep -rl --binary-files=without-match 'node-gyp-11-4-0-package-lock.json' --exclude-dir=.git . | paste -sd' ')"
```

```text
name=node-gyp version=11.4.0 lockfileVersion=3 packages=367
仓库内引用它的文件: ./nix/node-gyp-11-4-0.nix
```

唯一读者是 `nix/node-gyp-11-4-0.nix`,读法是把它**软链成 `package-lock.json`**:

`nix/node-gyp-11-4-0.nix:20-22 @ 863e313`

```nix
    postPatch = ''
      ln -s ${./node-gyp-11-4-0-package-lock.json} package-lock.json
    '';
```

因果链是:仓库用 npm 12(`nix/npm-12-0-2.nix`)→ npm 12 改了 node-gyp 的配置变量名 → nixpkgs 里的 node-gyp 不认 → 自建 node-gyp 11.4.0 → 但 node-gyp 的 GitHub tag 里**没有** lockfile,而 `buildNpmPackage` 需要一个 → 把 lockfile 抄进本仓库。补上最后一环的是 `patchedNpmConfigHook`:

`nix/lib.nix:56-58 @ 863e313`

```nix
    substituteInPlace $out/nix-support/setup-hook \
      --replace-fail 'npm_config_nodedir' 'npm_package_config_node_gyp_nodedir' \
      --replace-fail 'npm_config_node_gyp' 'npm_config_node_gyp=${node_gyp_11_4_0}/bin/node-gyp'
```

**5,246 行里没有一行需要精读,但整条链缺一环就说不通"为什么仓库里躺着别人的 lockfile"**。

npm 依赖的校验姿态也在这条链上:

`nix/lib.nix:206-212 @ 863e313`

```nix
  # npm dependencies for the workspace, shared by all members. importNpmLock
  # resolves each package from the lockfile's own `integrity` hashes, so the
  # lockfile is the single source of truth — no separate dependency hash to
  # keep in sync with it.
  npmDeps = importNpmLock.importNpmLock {
    npmRoot = npmDepsSrc;
  };
```

#### 2.11.4 重建范围控制

`pythonSrc` 是一个 `cleanSourceWith` 过滤器,把 JS/TS workspace(**从根 `package.json` 的 `workspaces` 字段动态推导**)、docs、website、docker、.github、tests、nix、skills、optional-skills、locales、optional-mcps 全部排除(排除清单在 `nix/lib.nix:116-173`)。

`nix/lib.nix:107-110 @ 863e313`

```nix
  pythonSrc = lib.cleanSourceWith {
    src = repoRoot;
    name = "hermes-python-source";
    filter =
```
目的一句话:**改一个 `.tsx` 不该重建 Python venv,改一个 `.py` 不该重建 TUI**。skills 被排除还有第二层理由——它们不进 wheel,而是走 `HERMES_BUNDLED_SKILLS` 软链(§2.11.2),所以"改 SKILL.md 不重建 venv"是免费的。

#### 2.11.5 NixOS 模块的两种模式

`nix/nixosModules.nix` 的头注释把设计交代得很完整:`container.enable = false`(默认)是原生 systemd 服务;`true` 则跑一个 OCI 容器(默认 Ubuntu 基底),**hermes 从 /nix/store 只读 bind-mount 进去,可写层留给 agent 自己 apt/pip/npm 装东西并跨重启保留**。环境变量走 `$HERMES_HOME/.env`,改环境变量不需要重建容器。

配置生成走 `nix/configMergeScript.nix`:Nix 侧的 attrset 转 JSON,再 `deep_merge` 进已存在的 `config.yaml`,Nix 键赢、用户键(skills/streaming 等)保留。`nix/checks.nix` 的 `config-roundtrip` 检查用 7 个场景钉住这套合并语义。

### 2.12 dev-sandbox.sh:安装器自己的测试床

`scripts/dev-sandbox.sh` 是本片里最容易被当成"辅助脚本"而错过的东西。它做的是:在 user / mount / pid / net 命名空间里造一个**假 Internet**,把 `scripts/install.sh` 真跑一遍。

- 阶段 1(本文件):建沙箱树、铸假 CA、用 `unshare` 建 user+net 命名空间,再 re-exec 进 `scripts/sandbox/stage2-run.sh`(**片外**);
- 阶段 2:bubblewrap 加 mount/pid 命名空间,跑载荷;
- HTTP(S) 走本地静态 MITM 代理;`github.com` 的 SSH 走沙箱内的 `git-upload-pack` shim,**碰不到宿主的 SSH 配置、agent、known_hosts**;
- `--from-main` / `--install-ref REF` 让它先装**上游的某个历史版本**,再测 `hermes update` ——"两个版本前的用户还能不能更新"这个问题因此是可执行的;
- `--root` 切 uid 0,因为 `install.sh` 的布局选择完全由 `id -u` 决定(§2.2),uid 是两种真实布局的唯一分水岭。

`nix/sandbox.nix` 把它包成 `packages.sandbox`,注入四个 `DEV_SANDBOX_*` 变量(真 CA、动态链接器、Node 目录、Electron 运行时库路径)与 `DEV_SANDBOX_ASSETS`——因为 Nix 把脚本作为**单个文件**导入 store,它旁边没有 `scripts/sandbox/` 了。

### 2.13 容器接驳的三个脚本

`scripts/docker_config_migrate.py` 与 `scripts/docker_rebootstrap_nous_session.py` 都由 `docker/stage2-hook.sh`(**片外,属 B 片**)在启动时调用,都以 `s6-setuidgid hermes` 降权跑,且**失败只 warn 不中断**。

`docker/stage2-hook.sh:453-454 @ 863e313`

```bash
    s6-setuidgid hermes "$INSTALL_DIR/.venv/bin/python" "$INSTALL_DIR/scripts/docker_config_migrate.py" \
        || echo "[stage2] Warning: docker_config_migrate.py failed; continuing"
```

`docker/stage2-hook.sh:489-492 @ 863e313`

```bash
        s6-setuidgid hermes "$INSTALL_DIR/.venv/bin/python" \
            "$INSTALL_DIR/scripts/docker_rebootstrap_nous_session.py" \
            "$HERMES_HOME/auth.json" \
            || echo "[stage2] Warning: docker_rebootstrap_nous_session.py failed; continuing"
```

后者的设计约束写得很清楚:

`scripts/docker_rebootstrap_nous_session.py:30-35 @ 863e313`

```python
- Pure stdlib, no hermes_cli imports: runs early in the boot hook, before the
  app venv/modules are guaranteed importable, as its own subprocess.
- Surgical: replaces ONLY ``providers.nous`` in the existing auth.json, leaving
  every other provider, the version, and any other top-level state untouched.
- Fail-safe: any parse/IO error leaves auth.json exactly as-is and exits 0 (a
  failed re-seed must never take the container further down than it already is).
```

它存在的原因是 stage2-hook 的种子逻辑只在**空卷**上生效(`[ ! -f auth.json ]`),那道守卫是有意的(防止重启覆盖健康的轮转过的 refresh token),于是需要一个**窄口子**用另一个环境变量 `HERMES_AUTH_JSON_REBOOTSTRAP` 来救已被判死的会话。

`scripts/hermes-gateway` 是第三个,但它的问题不是接驳,是**它是一条与 CLI 打架的平行路线**——见 §5 ■-1。

---

## 3. 接缝穷举

### 3.1 平台 × 架构矩阵

```verify
cd /home/user/hermes-agent && printf 'detect_os 分支: %s\n' "$(sed -n '504,540p' scripts/install.sh | grep -oE '^\s{8}[A-Za-z*|]+\)' | tr -d ' )' | paste -sd' ')" && printf 'node_arch 支持: %s\n' "$(sed -n '879,889p' scripts/install.sh | grep -oE '^\s+[a-z0-9_|]+\)' | tr -d ' )' | paste -sd' ')" && printf 'node_os 支持: %s\n' "$(sed -n '892,900p' scripts/install.sh | grep -oE '^\s+[a-z*]+\)' | tr -d ' )' | paste -sd' ')" && printf 'linux 包管理器: %s\n' "$(sed -n '1117,1121p' scripts/install.sh | grep -oE '^\s+[a-z|]+\)' | tr -d ' )' | paste -sd' ')"
```

```text
detect_os 分支: Linux* Darwin* CYGWIN*|MINGW*|MSYS* *
node_arch 支持: x86_64 aarch64|arm64 armv7l
node_os 支持: linux macos *
linux 包管理器: ubuntu|debian fedora arch
```

**逐项列全**:

| 面 | 取值(全部) | 锚点 |
|---|---|---|
| `install.sh` OS 分支 | `Linux*`(→ `android`/`termux` 或 `linux`)、`Darwin*`(→ `macos`)、`CYGWIN*\|MINGW*\|MSYS*`(→ **打印 install.ps1 命令并 `exit 1`**)、`*`(→ `unknown`,仅告警) | `scripts/install.sh:503-543` |
| `install.sh` Node 架构 | `x86_64`→x64、`aarch64\|arm64`→arm64、`armv7l`→armv7l、其它→放弃自动装(告警 + 手动链接) | `scripts/install.sh:879-889` |
| `install.sh` Node OS | `linux`→linux、`macos`→darwin、其它→放弃;Termux 走 `pkg install -y nodejs`,不下 tarball | `scripts/install.sh:863-900` |
| Node 自动安装矩阵 | 2 OS × 3 arch = **6 组合** + Termux 一条独立路径 | 同上 |
| Linux 包管理器 | `ubuntu\|debian`→`apt install -y`、`fedora`→`dnf install -y`、`arch`→`pacman -S --noconfirm`;**其它发行版无自动安装**(只给手动提示) | `scripts/install.sh:1117-1121` |
| 其它平台包管理 | macOS→`brew install`;Termux→`pkg install -y`(固定装 clang rust make pkg-config libffi openssl ca-certificates curl,外加缺的 ripgrep/ffmpeg) | `scripts/install.sh:1059-1113` |
| ripgrep 最后兜底 | `cargo install ripgrep`(有 cargo 时) | `scripts/install.sh:1184-1192` |
| Chromium 手动提示 | `ubuntu\|debian`、`arch`、`fedora\|rhel\|centos` | `scripts/install.sh:2708-2718` |
| `install.ps1` 架构 | CIM `Win32_Processor.Architecture`:12→arm64、9→x64、0→x86、5→arm;CIM 不可用则读 `PROCESSOR_ARCHITEW6432`/`PROCESSOR_ARCHITECTURE`(ARM64/AMD64/x86),再兜底按 `Is64BitOperatingSystem` 给 x64/x86 | `scripts/install.ps1:418-447` |
| `install.ps1` Git 资产 | arm64→`PortableGit-2.54.0-arm64.7z.exe`、x64→`PortableGit-2.54.0-64-bit.7z.exe`、**其它(x86/arm)→`MinGit-2.54.0-32-bit.zip` + 明确降级警告** | `scripts/install.ps1:1240-1252` |
| `install.ps1` Windows 包管理器 | winget(`BurntSushi.ripgrep.MSVC` / `Gyan.FFmpeg`)→ choco → scoop,三级 | `scripts/install.ps1:1611-1660` |

关键源码,`scripts/install.sh:879-889 @ 863e313`

```bash
    case "$arch" in
        x86_64)        node_arch="x64"    ;;
        aarch64|arm64) node_arch="arm64"  ;;
        armv7l)        node_arch="armv7l" ;;
        *)
            log_warn "Unsupported architecture ($arch) for Node.js auto-install"
            log_info "Install manually: https://nodejs.org/en/download/"
            HAS_NODE=false
            return 0
            ;;
    esac
```

`scripts/install.sh:1117-1121 @ 863e313`

```bash
    case "$DISTRO" in
        ubuntu|debian) pkg_install="apt install -y"   ;;
        fedora)        pkg_install="dnf install -y"   ;;
        arch)          pkg_install="pacman -S --noconfirm" ;;
    esac
```

### 3.2 命令行参数面

```verify
cd /home/user/hermes-agent && SH=$(awk 'NR>=96 && NR<=205 && /^        [-*]/ {gsub(/\)$/,""); gsub(/^ +/,""); if($0=="*")next; n=split($0,a,"|"); for(i=1;i<=n;i++) print a[i]}' scripts/install.sh | sort -u) && PS=$(awk 'NR>=15 && NR<=75' scripts/install.ps1 | grep -oE '^\s*\[(switch|string)\]\$[A-Za-z]+' | sed 's/.*\$/-/' | sort -u) && printf 'install.sh 选项 token=%d\ninstall.ps1 参数=%d\n同名可共用=%d: %s\n' "$(echo "$SH"|wc -l)" "$(echo "$PS"|wc -l)" "$(comm -12 <(echo "$SH") <(echo "$PS")|wc -l)" "$(comm -12 <(echo "$SH") <(echo "$PS")|paste -sd' ')"
```

```text
install.sh 选项 token=26
install.ps1 参数=17
同名可共用=8: -Branch -Commit -ForceCommit -IncludeDesktop -Json -Manifest -NonInteractive -Stage
```

`install.sh` 的 26 个 token 来自 `scripts/install.sh:95-205` 那个 `while`/`case` 的选项分支,其中 8 个分支额外接受 PascalCase 别名(即上面那 8 个同名项)。分支数:

```verify
cd /home/user/hermes-agent && awk 'NR>=96 && NR<=205 && /^        [-*]/ {gsub(/\)$/,""); gsub(/^ +/,""); if($0=="*")next; n++} END{print n" 个 case 选项分支(不含 * 兜底)"}' scripts/install.sh
```

```text
16 个 case 选项分支(不含 * 兜底)
```

**逐项对照表**(空格=该侧没有):

| 能力 | `scripts/install.sh` | `scripts/install.ps1` |
|---|---|---|
| 不建 venv | `--no-venv` | `-NoVenv` |
| 跳过 setup 向导 | `--skip-setup` | `-SkipSetup` |
| 跳过浏览器/Playwright | `--skip-browser` / `--no-playwright` | **无** |
| 不种内置技能(并写永久 opt-out 标记) | `--no-skills` | **无** |
| 分支 | `--branch` / `-Branch` | `-Branch` |
| 钉提交 | `--commit` / `-Commit` | `-Commit` |
| 允许回滚式钉提交 | `--force-commit` / `-ForceCommit` | `-ForceCommit` |
| 钉 tag | **无** | `-Tag` |
| 打印阶段清单 | `--manifest` / `-Manifest` | `-Manifest` |
| 跑单阶段 | `--stage` / `-Stage` | `-Stage` |
| JSON 结果帧 | `--json` / `-Json` | `-Json` |
| 非交互 | `--non-interactive` / `-NonInteractive` | `-NonInteractive` |
| 顺带建桌面 | `--include-desktop` / `-IncludeDesktop` | `-IncludeDesktop` |
| 代码目录 | `--dir` | `-InstallDir` |
| 数据目录 | `--hermes-home` | `-HermesHome` |
| 只补依赖 | `--ensure` | `-Ensure` |
| 帮助 | `-h` / `--help` | **无**(靠 PowerShell 自带 `-?`) |
| 只打印协议版本号 | **无** | `-ProtocolVersion` |
| 只打印解析出的路径(JSON) | **无** | `-ShowResolvedPaths` |
| 安装后补齐(= `-Ensure node,browser`) | **无** | `-PostInstall` |

`--ensure` / `-Ensure` 的取值面也不等价:

| 取值 | `install.sh`(`:2727-2762`) | `install.ps1`(`:4110-4142`) |
|---|---|---|
| `node` | `check_node`(必要时装) | `Test-Node`,失败 `exit 1` |
| `browser` | `check_node` + `ensure_browser`(npm 全局 + Chromium) | `Test-Node` + `Install-AgentBrowser`,无 node 则 `exit 1` |
| `ripgrep` | 真装(走 `install_system_packages`) | **只打印 `scoop install ripgrep`** |
| `ffmpeg` | 真装 | **只打印 `scoop install ffmpeg`** |
| 未知 | `log_warn` 后继续 | `Write-Err` + `exit 1` |

### 3.3 环境变量面

三分法的定义写在探针脚本的 docstring 里(A=自默认 `NAME="${NAME:-默认}"`;B=只读从不赋值;C=既读又赋值,机械上判不了、逐条裁决)。

```verify
python3 data/r11a/probes/probe_a_env_face.py /home/user/hermes-agent | sed -n '1,30p;/install.ps1] \$env:/p'
```

```text
[scripts/install.sh] 输入面 = A自默认 6 + B纯外部读 11 = 17
  A DESKTOP_BUILD_TIMEOUT
  A HERMES_HOME
  A NODE_DEPS_TIMEOUT
  A TERM
  A UV_PYTHON_BIN_DIR
  A UV_PYTHON_INSTALL_DIR
  B APPLE_SIGNING_IDENTITY
  B CSC_LINK
  B ELECTRON_CACHE
  B HERMES_INSTALL_DIR
  B PREFIX
  B PYTHONHOME
  B PYTHONPATH
  B SHELL
  B TERMUX_VERSION
  B VERSION_ID
  B XDG_CACHE_HOME
[scripts/install.sh] C 读+赋值,需人工裁决 10: AGENT_BROWSER_EXECUTABLE_PATH ANDROID_API_LEVEL DETECTED_BROWSER_EXECUTABLE DISTRO DISTRO_VERSION ELECTRON_MIRROR INSTALL_DIR PLAYWRIGHT_HOST_PLATFORM_OVERRIDE UV_CMD VIRTUAL_ENV

[scripts/lib/node-bootstrap.sh] 输入面 = A自默认 3 + B纯外部读 4 = 7
  A HERMES_HOME
  A HERMES_NODE_MIN_VERSION
  A HERMES_NODE_TARGET_MAJOR
  B HERMES_NPM_TARGET_RANGE
  B NVM_DIR
  B PREFIX
  B TERMUX_VERSION
[scripts/lib/node-bootstrap.sh] C 读+赋值,需人工裁决 1: HERMES_NODE_SKIP_LINKS

[scripts/install.ps1] $env: 读取 33 个:
```

**C 桶逐条裁决**(`install.sh` 的 10 条,全部读过):

| 名字 | 裁决 | 依据 |
|---|---|---|
| `AGENT_BROWSER_EXECUTABLE_PATH` | **是输入** | `scripts/install.sh:1994` 的 `Honor ONLY an explicit, user-set`(脚本另有 `unset`,是为了清 Snap 覆盖) |
| `ANDROID_API_LEVEL` | **是输入** | `scripts/install.sh:1464` 的 `if [ -z "${ANDROID_API_LEVEL:-}" ]; then`(未设才 `getprop`,再退回 24) |
| `ELECTRON_MIRROR` | **是输入** | `scripts/install.sh:3054` 的 `[ -z "${ELECTRON_MIRROR:-}" ]`(只有用户没设时才自动换镜像);`scripts/install.sh:3057` 的 `set ELECTRON_MIRROR yourself` |
| `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE` | **是输入** | `scripts/install.sh:2205` 的 `An operator-provided PLAYWRIGHT_HOST_PLATFORM_OVERRIDE is always respected:` |
| `VIRTUAL_ENV` | 边界:脚本会保存/恢复继承值,但不作旋钮用 | `scripts/install.sh:2929` 的 `local _prev_venv="${VIRTUAL_ENV:-}"` |
| `DISTRO` / `DISTRO_VERSION` | 内部 | `detect_os` 设定 |
| `INSTALL_DIR` | 内部(对应的外部旋钮是 `HERMES_INSTALL_DIR` / `--dir`) | `scripts/install.sh:52` 的 `if [ -n "${HERMES_INSTALL_DIR:-}" ]; then` |
| `UV_CMD` | 内部 | `install_uv` 设定 |
| `DETECTED_BROWSER_EXECUTABLE` | 内部 | `scripts/install.sh:67` 的 `DETECTED_BROWSER_EXECUTABLE=""` |

`node-bootstrap.sh` 的 `HERMES_NODE_SKIP_LINKS`:**是输入**。

`scripts/lib/node-bootstrap.sh:305-309 @ 863e313`

```bash
    # HERMES_NODE_SKIP_LINKS=1: the caller only wants the private managed tree
    # (e.g. the EBADENGINE recovery provisioning a runtime alongside a working
    # system Node). Skipping the links keeps the user's own node/npm first on
    # PATH instead of shadowing them with ours.
    if [ "${HERMES_NODE_SKIP_LINKS:-0}" != "1" ]; then
```

**结论(逐项)**:`scripts/install.sh` 的环境变量输入面 = 17 + 4 = **21 个**;`scripts/lib/node-bootstrap.sh` = 7 + 1 = **8 个**。

安装器**导出**给子进程的(另一张面):

```verify
cd /home/user/hermes-agent && grep -oE '^[[:space:]]*export [A-Z][A-Z0-9_]*=' scripts/install.sh | sed 's/.*export //; s/=//' | sort -u | paste -sd' ' && grep -cE '^[[:space:]]*export [A-Z][A-Z0-9_]*=' scripts/install.sh
```

```text
PATH UV_NO_CONFIG UV_PYTHON UV_PYTHON_BIN_DIR UV_PYTHON_INSTALL_DIR VIRTUAL_ENV
15
```

去重后 **6 个**(15 处 export 语句)。其中 `UV_NO_CONFIG=1` 在文件第 33 行、任何逻辑之前就 export,防的是 `sudo -u <user>` 下 uv 去读**错误那个用户的** `uv.toml` / `pyproject.toml`(#21269)。

`scripts/install.ps1` 侧读 `$env:` 的名字共 **33 个**(见上探针输出末行;PowerShell 里 `$env:X` 只可能是环境变量,不需要三分法)。

### 3.4 stage 面

见 §2.5 的枚举命令与输出。补充:`install.sh` 的 11 个名字里 `desktop` **只在 `--include-desktop` 时进 manifest**,所以默认 manifest 是 10 个;`install.ps1` 同理(`scripts/install.ps1:3958-3964`),默认 15 个。

`scripts/install.sh:321-323 @ 863e313`

```bash
    local desktop_stage=""
    if [ "$INCLUDE_DESKTOP" = true ]; then
        desktop_stage='{"name":"desktop","title":"Build desktop app","category":"runtime","needs_user_input":false},'
```

### 3.5 Nix 对外输出面

```verify
python3 data/r11a/probes/probe_a_nix_surface.py /home/user/hermes-agent
```

```text
systems (3): x86_64-linux aarch64-linux aarch64-darwin
packages (10): node-gyp default sandbox minimal messaging tui web desktop update-npm-lockfile configKeys
checks (17): cross-eval build-package build-devshell package-contents entry-points-sync cli-commands bundled-skills bundled-plugins bundled-locales bundled-mcps bundled-tui hermes-node managed-guard extra-python-packages extra-dependency-groups messaging-variant config-roundtrip
  其中三系统都建 (3): cross-eval build-package build-devshell
  其中仅 Linux (14, 见 nix/checks.nix:77): package-contents entry-points-sync cli-commands bundled-skills bundled-plugins bundled-locales bundled-mcps bundled-tui hermes-node managed-guard extra-python-packages extra-dependency-groups messaging-variant config-roundtrip
devShells (1): nix/devShell.nix:default
overlays (1): nix/overlays.nix:default
nixosModules (1): nix/nixosModules.nix:default
services.hermes-agent 顶层选项 (23): enable package user group createUser stateDir workingDirectory configFile settings environmentFiles environment authFile authFileForceOverwrite documents mcpServers extraArgs extraPackages extraPlugins extraPythonPackages extraDependencyGroups restart restartSec addToSystemPackages
services.hermes-agent.container.* (6): enable backend extraVolumes extraOptions image hostUsers
```

**枚举方法的局限要如实说**:本容器**没有 nix**——

```verify
command -v nix >/dev/null 2>&1 && echo "nix: yes" || echo "nix: NO"
```

```text
nix: NO
```

所以上表是**对源文件做结构化文本抽取**,不是 `nix flake show` 的求值结果。抽取规则(见探针 docstring):在 `packages = {` / `checks = {` 块内取"恰好深一层缩进"的 `x = ...` 与 `inherit a b;`;`flake.overlays.*` / `flake.nixosModules.*` 按前缀抓;选项按 `mkOption`/`mkEnableOption` 加缩进分层。一个用 `//` 或 `lib.optionalAttrs` 动态拼进去的输出**会被漏掉**——已知 `nix/checks.nix:77` 就是这种写法,本脚本靠花括号计数越过了它(所以 17 是并集),但这条局限对别处仍然成立。真求值枚举列进 §6 待提供项。

`packages` 的 10 个里,`configKeys` 定义在 `nix/checks.nix:36`(`packages.configKeys = configKeys;`)而不是 `nix/packages.nix`——它跑一段 Python 把 `hermes_cli.config.DEFAULT_CONFIG` 的叶子路径导出成 JSON,文档 `website/docs/getting-started/nix-setup.md:255` 教用户 `nix build .#configKeys && cat result`。

`nix/checks.nix` 的三系统/仅 Linux 分界:

`nix/checks.nix:77 @ 863e313`

```nix
      } // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
```

### 3.6 release.py 的步骤面

见 §2.9 的 9 步表。参数面 5 个(`--bump` / `--publish` / `--date` / `--first-release` / `--output`),无子命令:

```verify
cd /home/user/hermes-agent && grep -c 'parser.add_argument' scripts/release.py && grep -oE 'add_argument\("(--[a-z-]+)"' scripts/release.py | sed 's/.*"\(.*\)"/\1/' | paste -sd' '
```

```text
5
--bump --publish --date --first-release --output
```

---

## 4. 端到端链(逐跳锚点)

### 4.1 链一:`curl | bash` → `.install_method` → `hermes update` 的行为

**跳 1 — 触发**。`website/docs/getting-started/installation.md:25` 给的命令是
`curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash`。管道进 bash ⇒ stdin 不是 TTY:

`scripts/install.sh:88-92 @ 863e313`

```bash
if [ -t 0 ]; then
    IS_INTERACTIVE=true
else
    IS_INTERACTIVE=false
fi
```

于是后续所有交互都改从 `/dev/tty` 读(`prompt_yes_no` 的第三分支,`scripts/install.sh:366-368`;向导 `scripts/install.sh:2431` 的 `< /dev/tty`)。

**跳 2 — 分发**。无 `--manifest`/`--stage`/`--ensure` ⇒ 走 `main()`(§2.1 的 dispatch 块)。

**跳 3 — 落地目录**。`resolve_install_layout` 定 `INSTALL_DIR`(§2.2)。

**跳 4 — 取源码**。`clone_repo` 先 SSH 后 HTTPS,失败即 `rm -rf` 半个 clone。

`scripts/install.sh:1351-1358 @ 863e313`

```bash
        log_info "Trying SSH clone..."
        if GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5" \
           git clone --depth 1 --branch "$BRANCH" "$REPO_URL_SSH" "$INSTALL_DIR" 2>/dev/null; then
            log_success "Cloned via SSH"
        else
            rm -rf "$INSTALL_DIR" 2>/dev/null  # Clean up partial SSH clone
            log_info "SSH failed, trying HTTPS..."
            if git clone --depth 1 --branch "$BRANCH" "$REPO_URL_HTTPS" "$INSTALL_DIR"; then
```

**跳 5 — 装依赖**。`setup_venv` → `install_deps`(Tier 0 哈希校验,§2.3)。

**跳 6 — 命令落地**。`setup_path` 写三个 shim 到 `get_command_link_dir()`(§2.2)。

**跳 7 — 打戳**。整装流程的最后一行,与 `--stage complete` 里的那一行是同一句:

`scripts/install.sh:3272 @ 863e313`

```bash
            echo "git" > "$INSTALL_DIR/.install_method"
```

**跳 8 — 运行时读它**。

`hermes_cli/config.py:457-461 @ 863e313`

```python
    # 1. Code-scoped stamp — authoritative, immune to shared $HERMES_HOME.
    try:
        method = (root / ".install_method").read_text(encoding="utf-8").strip().lower()
        if method in supported_methods:
            return method
```

**跳 9 — 行为分叉**。

`hermes_cli/main.py:9121-9127 @ 863e313`

```python
    install_method = detect_install_method(PROJECT_ROOT)
    if install_method == "docker":
        print(format_docker_update_message())
        sys.exit(1)

    if install_method in {"nix", "nixos"}:
        print(recommended_update_command_for_method(install_method))
```

**这条链上最贵的一课**写在 `hermes_cli/config.py:425-437`:戳**必须**放在代码树旁边而不是 `$HERMES_HOME`,因为 Docker 文档鼓励把 `~/.hermes` bind-mount 进容器(`~/.hermes:/opt/data`),容器每次启动都往共享的 home 里盖一个 `docker` 戳,宿主上的 git 安装读到它之后 `hermes update` 就一直拒绝执行。修法有两层:戳改成代码域的,**外加**对遗留 home 域戳做自愈——只有真在容器里时才承认 `docker` 值。

`hermes_cli/config.py:471-477 @ 863e313`

```python
            (get_hermes_home() / ".install_method")
            .read_text(encoding="utf-8")
            .strip()
            .lower()
        )
        if method in supported_methods and not (method == "docker" and not _running_in_container()):
            return method
```

**Windows 侧这条链断了一节**:`scripts/install.ps1` 从不写 `.install_method`。

```verify
cd /home/user/hermes-agent && printf 'install.ps1 里 install_method = %s 处\n' "$(grep -c 'install_method' scripts/install.ps1)"
```

```text
install.ps1 里 install_method = 0 处
```

后果不是坏结果而是**换了条推导路径**:`detect_install_method` 会一路落到第 5 条"有 `.git` 目录 ⇒ `git`"。git clone 路径和 ZIP 兜底路径(§2.6,那条路径显式 `git init` + `fetch`)都留下 `.git`,所以结论仍是 `git`;但 Windows 安装因此**与一个开发者的裸 checkout 不可区分**,而 POSIX 安装是可区分的。记为 §5 ◇-2。

### 4.2 链二:`release.py --publish` → 版本文件 → Nix 派生版本 / 技能缓存键

**跳 1 — 触发**。人工。**没有任何工作流跑它**:

```verify
cd /home/user/hermes-agent && printf '.github 里出现 release.py 的文件: %s\n' "$(grep -rl 'release.py' .github/ 2>/dev/null | paste -sd' ')" && printf '其中真正执行它的行数: %s\n' "$(grep -rnE '(python3?|uv run)[^|]*scripts/release\.py' .github/ 2>/dev/null | wc -l)"
```

```text
.github 里出现 release.py 的文件: .github/workflows/contributor-check.yml
其中真正执行它的行数: 0
```

`contributor-check.yml` 只是 `grep -qF` 它的 `LEGACY_AUTHOR_MAP` 来判断某个邮箱是否已有映射。

`.github/workflows/contributor-check.yml:59 @ 863e313`

```yaml
            if ! grep -qF "\"${email}\"" scripts/release.py 2>/dev/null; then
```

**跳 2 — 改版本文件**。`update_version_files` 写三处(见 §2.9)。基线现值:`hermes_cli/__init__.py:17-18` 是 `0.20.0` / `2026.8.3`。

`pyproject.toml:5 @ 863e313`

```toml
version = "0.20.0"
```

**跳 3 — 打标签并推**。`git tag -a v<CalVer>` 之后:

`scripts/release.py:2584-2585 @ 863e313`

```python
        # Push
        push_result = git_result("push", "origin", "HEAD", "--tags")
```

**跳 4a — Nix 派生版本随之而动**。

`nix/hermes-agent.nix:163 @ 863e313`

```nix
  version = (fromTOML (builtins.readFile ../pyproject.toml)).project.version;
```

**跳 4b — 技能索引缓存键随之失效**,所以一次发布必然让所有用户的技能索引缓存作废、重建。

`hermes_cli/main.py:891 @ 863e313`

```python
        return f"skills:{__version__}:{__release_date__}:{stat.st_mtime_ns}:{stat.st_size}"
```

**跳 5 — 安装器不读版本号**。`scripts/install.sh` 装的是 `--branch main` 的 tip,不是最新 tag;`--commit` 才能钉。也就是说 **CalVer 标签是给人和 GitHub Releases 看的,不在装机路径上**。

---

## 5. 记号(■/▲/◇/◎)与负结论

### ■-1 `scripts/hermes-gateway install` 会覆盖 CLI 管理的那个 systemd unit,而 CLI 的"遗留 unit"安全扫描认不出它

`scripts/hermes-gateway:53 @ 863e313`

```python
    return Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"
```

`scripts/hermes-gateway:48 @ 863e313`

```python
SERVICE_NAME = "hermes-gateway"
```

CLI 那边:

`hermes_cli/gateway.py:1838-1842 @ 863e313`

```python
def get_systemd_unit_path(system: bool = False) -> Path:
    name = get_service_name()
    if system:
        return Path("/etc/systemd/system") / f"{name}.service"
    return Path.home() / ".config" / "systemd" / "user" / f"{name}.service"
```

`get_service_name()` 在默认 profile 下返回 `_SERVICE_BASE`:

`hermes_cli/gateway.py:1750 @ 863e313`

```python
_SERVICE_BASE = "hermes-gateway"
```

**两者是同一个路径**。但生成的 unit 完全不同:

`scripts/hermes-gateway:88-93 @ 863e313`

```python
[Service]
Type=simple
ExecStart={python_path} {script_path} run
WorkingDirectory={working_dir}
Restart=on-failure
RestartSec=30
```

CLI 侧写的 unit 走 `hermes gateway` / `gateway/run.py` 一类入口。CLI 有一套"遗留 unit"检测(`hermes_cli/gateway.py:2121-2155`),但它的允许名单只有一个名字:

`hermes_cli/gateway.py:2096 @ 863e313`

```python
_LEGACY_SERVICE_NAMES: tuple[str, ...] = ("hermes.service",)
```

ExecStart 标记表也只认五个串:

`hermes_cli/gateway.py:2100-2106 @ 863e313`

```python
_LEGACY_UNIT_EXECSTART_MARKERS: tuple[str, ...] = (
    "hermes_cli.main gateway",
    "hermes_cli/main.py gateway",
    "gateway/run.py",
    " hermes gateway ",
    "/hermes gateway ",
)
```

**`scripts/hermes-gateway` 那个 ExecStart(`{python_path} {script_path} run`)一个都不匹配**,而且它写的名字就是"当前名"而非"遗留名",所以那套自愈机制**结构上不可能**发现它。

后果:任何跑过 `./scripts/hermes-gateway install` 的用户,其 `hermes gateway install` 会被静默覆盖(反之亦然),而 `hermes gateway migrate-legacy` 报告"没有遗留 unit"。

严重性被下面这条压低了——但没有归零:

**负结论-1(带搜索面)**:`scripts/hermes-gateway` 在全仓**没有任何其它引用**。

```verify
cd /home/user/hermes-agent && printf 'scripts/hermes-gateway 被自身以外引用: %s 处\n' "$(grep -rn --binary-files=without-match 'scripts/hermes-gateway' --exclude-dir=.git . | grep -vc '^\./scripts/hermes-gateway:')"
```

```text
scripts/hermes-gateway 被自身以外引用: 0 处
```

**搜索面**:`grep -rn` 全仓(排除 `.git`),模式为字面量 `scripts/hermes-gateway`,含二进制文件按文本处理(`--binary-files=without-match` 只是跳过真二进制),再排除文件自身的行。**没有排除任何目录**(docs、tests、workflows、TS 全在内)。局限:只搜了这一个字面串;若有人用 `os.path.join("scripts", "hermes-gateway")` 之类拼出来,本命令看不见。所以准确说法是:**没有任何文件以字面路径引用它**,它既不在 CI、也不在文档、也不在包数据里,但它 `chmod +x`、仍可被用户直接跑,且它 import 的 `gateway.run.start_gateway` 在基线里仍然存在——**它不是死代码,是一条活着的平行路线**。

`gateway/run.py:26360 @ 863e313`

```python
async def start_gateway(config: Optional[GatewayConfig] = None, replace: bool = False, verbosity: Optional[int] = 0) -> bool:
```

### ■-2 两个安装器都对用户说 "Hermes requires Node >=26",然后装 Node 22

`scripts/install.sh:59-60 @ 863e313`

```bash
PYTHON_VERSION="3.11"
NODE_VERSION="22"
```

判定门槛是 ≥22.22:

`scripts/install.sh:790-798 @ 863e313`

```bash
node_satisfies_build() {
    local ver="${1#v}"
    local major="${ver%%.*}"
    local minor="${ver#*.}"; minor="${minor%%.*}"
    case "$major" in ''|*[!0-9]*) return 1 ;; esac
    case "$minor" in ''|*[!0-9]*) minor=0 ;; esac
    if [ "$major" -ge 22 ] && { [ "$major" -gt 22 ] || [ "$minor" -ge 22 ]; }; then return 0; fi
    return 1
}
```

而没过门槛时打印的消息是:

`scripts/install.sh:852-853 @ 863e313`

```bash
    if command -v node &> /dev/null; then
        log_warn "Node.js $(node --version) is too old (Hermes requires Node >=26) — installing Hermes-managed Node $NODE_VERSION..."
```

**同一行里自相矛盾**:声称需要 ≥26,紧接着说要装 `$NODE_VERSION`(=22)。`scripts/install.ps1:1451` 是完全一样的措辞(`Write-Warn "Node.js $version is too old (Hermes requires Node >=26)"`),`scripts/install.ps1:384` 也是 `$NodeVersion = "22"`。

真正的**四套 Node 政策**:

```verify
cd /home/user/hermes-agent && grep -hn 'NODE_VERSION="22"' scripts/install.sh && grep -hn '^\$NodeVersion' scripts/install.ps1 && grep -hn 'nodejs_26,' nix/lib.nix && grep -hn 'HERMES_NODE_TARGET_MAJOR=' scripts/lib/node-bootstrap.sh && grep -hn 'NODE_MAJOR" -ge 26' nix/checks.nix && python3 -c "import json;print('package.json engines:', json.load(open('package.json'))['engines'])"
```

```text
60:NODE_VERSION="22"
384:$NodeVersion = "22"
27:  nodejs_26,
27:HERMES_NODE_TARGET_MAJOR="${HERMES_NODE_TARGET_MAJOR:-22}"
273:          test "$NODE_MAJOR" -ge 26 || \
package.json engines: {'node': '>=22.22.0', 'npm': '<11.10.0 || >=11.17.0'}
```

即:`package.json` 说 ≥22.22;两个安装器装 22 且按 ≥22.22 判;`node-bootstrap.sh` 目标 22、下限 20;Nix 走 nodejs_26 并**断言** ≥26:

`nix/checks.nix:272-274 @ 863e313`

```nix
          NODE_MAJOR=$("$HERMES_NODE" --version | sed 's/^v//' | cut -d. -f1)
          test "$NODE_MAJOR" -ge 26 || \
            (echo "FAIL: Node v$NODE_MAJOR < 26, Hermes requires Node 26"; exit 1)
```

**判定**:Nix 与安装器给出的运行时 Node 大版本不同(26 vs 22)本身可以是有意的(Nix 用 nixpkgs 的新 Node);■ 落在**那句用户可见的消息**——它对着自己下一句话撒谎,任何按它行事的人都会去装一个安装器自己都不装的版本。`website/docs/getting-started/installation.md:93` 写的是 "Node.js v22",与代码一致,所以**文档不是错的一方**。

### ◇-1 `--no-skills` 与 `--skip-browser` 在 Windows 上不存在,且 `--no-skills` 的语义是跨轮持久的

```verify
cd /home/user/hermes-agent && for t in NoSkills SkipBrowser no-bundled-skills; do printf 'install.ps1 里 %-18s = %s 处\n' "$t" "$(grep -c -- "$t" scripts/install.ps1)"; done && printf 'install.sh  里 %-18s = %s 处\n' 'no-bundled-skills' "$(grep -c 'no-bundled-skills' scripts/install.sh)"
```

```text
install.ps1 里 NoSkills           = 0 处
install.ps1 里 SkipBrowser        = 0 处
install.ps1 里 no-bundled-skills  = 0 处
install.sh  里 no-bundled-skills  = 3 处
```

POSIX 侧 `--no-skills` 不只是"这次不装",它写 `$HERMES_HOME/.no-bundled-skills` 这个标记,`skills_sync.py` 和 `hermes update` 都认它,**以后每次更新都不再注入内置技能**(`scripts/install.sh:1969-1978`)。Windows 用户拿不到"白板 profile"这个能力,也拿不到该标记的持久语义。

反向的不对称:`install.ps1` 有一个 `platform-sdks` 阶段(`Install-PlatformSdks`,`scripts/install.ps1:3597`),按 `.env` 里实际配了哪些平台 token 去 `ensurepip` + 定向补装 SDK;`install.sh` 完全没有对应物(`grep -c 'platform-sdks' scripts/install.sh` = 0,`grep -c 'ensurepip'` = 0)。

### ◇-2 `.install_method` 只有 POSIX 侧写

见 §4.1 末尾。

### ◇-3 三个安装器测试里只有一个接进了 CI

```verify
cd /home/user/hermes-agent && for t in test-install-ps1-longpath.ps1 test-install-ps1-stage-protocol.ps1 test-install-ps1-gitbash-compatibility.ps1; do printf '%-45s .github/workflows 引用=%s\n' "$t" "$(grep -rl "$t" .github/workflows/ 2>/dev/null | wc -l)"; done
```

```text
test-install-ps1-longpath.ps1                 .github/workflows 引用=1
test-install-ps1-stage-protocol.ps1           .github/workflows 引用=0
test-install-ps1-gitbash-compatibility.ps1    .github/workflows 引用=0
```

有意思的是 `.github/workflows/installer-tests.yml:3-7` 的头注释自己说:"Before this workflow existed the files were in the tree but nothing ever ran them."——**这次修复只覆盖了三分之一**,另外两个仍然是"在树里但没人跑"。(CI 文件本身属 B 片,此处只作为 A 片文件"是否被执行"的判据。)

### ▲-1 `website/docs/getting-started/platform-support.md:36` 把 Nix 的安装方式写成 `install.sh`

`website/docs/getting-started/platform-support.md:36 @ 863e313`

> | **Nix** (MacOS, Linux, NixOS)  | [`install.sh`](./nix-setup.md)                                       | Breaks often due to node.js packaging woes. Best of luck~! &lt;3             |

这一整行讲的是 Tier 2 表格里 Nix 那一行的"Installation methods"列,标题是 "## Tier 2"(`website/docs/getting-started/platform-support.md:26`),列头是 "Installation methods"(`:33`)。**该列填的是 `install.sh`,链接却指向 `nix-setup.md`**。

代码侧:`scripts/install.sh` 里没有任何 nix 相关代码路径。

```verify
cd /home/user/hermes-agent && printf 'install.sh 里 nix(大小写不敏感,含 unix 在内)= %s 处;其中 unix = %s 处\n' "$(grep -icE 'nix' scripts/install.sh)" "$(grep -icE 'unix' scripts/install.sh)"
```

```text
install.sh 里 nix(大小写不敏感,含 unix 在内)= 0 处;其中 unix = 0 处
```

**搜索面**:整份 `scripts/install.sh`,大小写不敏感的子串 `nix`(会连带命中 `unix`/`Unix`,实测 0),未排除注释与字符串。而它指向的 `website/docs/getting-started/nix-setup.md:34-54` 给出的实际安装方式是 `nix run github:NousResearch/hermes-agent#desktop` / `nix profile install ...`,同页 `:24` 还明说 "The Nix flake replaces all of that"。**同一句里的其余部分**("(MacOS, Linux, NixOS)"、"Breaks often due to node.js packaging woes")与 flake 的三个 system 和 §2.11.3 的 node-gyp/npm 折腾一致,不构成 ▲。

### ◎-1 `nix/checks.nix` 头注释说 "Checks are Linux-only",实为 17 个里 3 个跨平台

`nix/checks.nix:3-5` 说 checks 是 Linux-only、"The package and devShell still work on macOS";而 `cross-eval` / `build-package` / `build-devshell` 三个确实在三个 system 上都定义(§3.5)。这三个建的恰好就是"package 和 devShell",所以**字面为真、只是保守**,按 CLAUDE.md 的记号定义计 ◎ 不计 ▲。

### 负结论-2:`scripts/release.py` 不产任何校验和/签名

```verify
cd /home/user/hermes-agent && printf 'release.py 命中 sha256|sha512|md5|gpg|sigstore|cosign|minisign|checksum|hashlib|--sign 的行数: %s\n' "$(grep -cniE 'sha256|sha512|md5|gpg|sigstore|cosign|minisign|checksum|hashlib|--sign' scripts/release.py)"
```

```text
release.py 命中 sha256|sha512|md5|gpg|sigstore|cosign|minisign|checksum|hashlib|--sign 的行数: 0
```

**搜索面**:只搜了 `scripts/release.py` 这一个文件,大小写不敏感,10 个模式(散列算法 3 个、签名工具 4 个、通用词 2 个、`git tag --sign` 的旗标 1 个)。**没有搜**:`.github/workflows/`(是否有工作流对 release 产物签名,属 B 片)、`pyproject.toml` 的构建后端、Docker 镜像签名。所以准确说法是:**这个脚本本身既不生成也不校验任何散列或签名**;它产出的"制品"是一个 git 标签和一个 GitHub Release 的说明文本,真正的分发物是 git 仓库,而安装器对它也不做签名校验(§2.3 第 3 条)。

### 负结论-3:两个安装器对下载物都不做校验和验证

**搜索面**:

```verify
cd /home/user/hermes-agent && printf 'install.sh 命中 %s 处: %s\n' "$(grep -cEi 'sha256|shasum|checksum|gpg|signature|--verify' scripts/install.sh)" "$(grep -nEi 'sha256|shasum|checksum|gpg|signature|--verify' scripts/install.sh | cut -d: -f1 | paste -sd,)" && printf 'install.ps1 命中 %s 处: %s\n' "$(grep -cEi 'sha256|checksum|Get-FileHash|Authenticode|signature' scripts/install.ps1)" "$(grep -nEi 'sha256|checksum|Get-FileHash|Authenticode|signature' scripts/install.ps1 | cut -d: -f1 | paste -sd,)"
```

```text
install.sh 命中 4 处: 1236,1381,1547,2829
install.ps1 命中 2 处: 2413,3327
```

逐条看过:`scripts/install.sh` 的 `:1236` / `:1381` 是 `git rev-parse --verify`,`:1547` 是 §2.3 引过的那段 uv.lock 注释,`:2829` 是 macOS 桌面临时签名的注释;`scripts/install.ps1` 的 `:2413` 是同一段 uv.lock 注释,`:3327` 是一句 npm 证书提示。**没有一处是对已下载文件计算并比对散列**。局限:只搜了这两个文件,没搜它们调用的外部安装器(astral 的 `install.sh` 自身可能校验其下载物,本轮未查)。

---

## 6. 待提供项(缺的凭据 / 依赖 / 环境)

| 缺什么 | 挡住了什么 | 备注 |
|---|---|---|
| `nix`(本容器无) | `nix flake show` / `nix eval` 的**求值式**输出面枚举;§3.5 现在是文本抽取 | 有 nix 后应复核 `packages`/`checks` 是否与文本抽取一致 |
| `pwsh` / `powershell`(本容器无) | 跑不了 `scripts/tests/test-install-ps1-*.ps1` 三个测试;install.ps1 的行为断言只能读代码 | 三者中两者 CI 也没跑(§5 ◇-3) |
| Windows / macOS / Termux 机器 | 两个安装器的真实端到端验证 | POSIX 侧有 `scripts/dev-sandbox.sh` 可在 Linux 上做假 Internet 全流程验证,**但需要 bubblewrap + unshare 权限**,本轮未尝试 |
| GitHub token | `scripts/build_skills_index.py` 的实跑(它爬 6 个源) | 无 token 时脚本自己会提示 "Set GITHUB_TOKEN for better results"(`scripts/build_skills_index.py:250`) |
| 可推送的 git 远端 + `gh` 登录 | `scripts/release.py --publish` 的实跑 | 干跑(不带 `--publish`)不需要凭据,但需要仓库有 `v20*` 标签或 `--first-release` |

---

## 7. 移交项

| # | 锚点 + 摘录 | 一句话现象 | 建议 |
|---|---|---|---|
| H-R11A-A-a | `hermes_cli/gateway.py:2096`:`_LEGACY_SERVICE_NAMES: tuple[str, ...] = ("hermes.service",)` | CLI 的遗留 unit 扫描只认 `hermes.service` 这一个名字,而 `scripts/hermes-gateway` 写的是**当前名** `hermes-gateway.service`,ExecStart 也不匹配任何标记,于是这条冲突结构上无法被检出 | 后续若做「网关服务安装」专题,把 `hermes_cli/gateway.py` 的 unit 生命周期(install / migrate-legacy / 多 profile 后缀)整片读掉,并确认 `scripts/hermes-gateway` 是否应判为应删 |
| H-R11A-A-b | `scripts/install.sh:853` 的 `Hermes requires Node >=26` | 该行消息说需要 Node ≥26,同一行随即装 `$NODE_VERSION`=22;`scripts/install.ps1:1451` 同样措辞 | 若做「版本与兼容性」专题,把 Node/npm/Python 三条版本线在 install.sh / install.ps1 / node-bootstrap.sh / nix/lib.nix / package.json / pyproject.toml 六处的取值做一张全表 |
| H-R11A-A-c | `scripts/install.sh:1610` 的 `local _BROKEN_EXTRAS=()` | 三级降级梯的第二级("all minus known-broken")当前**等价于第一级**,因为坏 extra 列表是空的;这是一个留白的应急位,不是活的逻辑 | 读 `pyproject.toml` 的 extras 拓扑时一并核对 `[all]` 的成员与各平台 extra 的可解性 |
| H-R11A-A-d | `nix/checks.nix:36`:`packages.configKeys = configKeys;` | 一个 `packages.*` 输出定义在 `checks.nix` 里而不是 `packages.nix`,任何"只读 packages.nix 就以为拿全了输出面"的做法都会漏掉它 | 若后续要做 flake 输出面的求值式复核,以此为回归用例 |
| H-R11A-A-e | `scripts/dev-sandbox.sh:22`:`SANDBOX_ASSETS="${DEV_SANDBOX_ASSETS:-$SCRIPT_DIR/sandbox}"` | 沙箱依赖 `scripts/sandbox/` 下四个资产(`proxy.py` `ssh-shim.sh` `openssl.cnf` `stage2-run.sh`),它们**不在本片清单里**,本片只交代了调用关系没读实现 | `scripts/sandbox/` 归哪一层需要在台账里确认;它是"安装器可验证性"的另一半 |

---

## 8. 附:本片没做的事(边界声明)

- `.github/workflows/*`(含 `installer-tests.yml`、`skills-index.yml`、`deploy-site.yml`)属 **B 片**,本片只在需要判断"A 片的某个文件是否被执行"时引用其行号。
- `docker/`(含 `stage2-hook.sh`、s6-rc 服务目录)属 **B 片**,本片只交代了 `scripts/docker_*.py` 被它调用的位置。
- `scripts/sandbox/` 四个资产不在本片清单(见 H-R11A-A-e)。
- `apps/desktop/electron/bootstrap-runner.ts` 是 stage 协议的**驱动方**,片外;本片引用它是为了证明"POSIX 与 Windows 是两套调用",不对其实现做断言。
