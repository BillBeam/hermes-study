# r11a 片B · CI 与运行时容器

> 底稿(证据层)。求全求证,不求好读。
> 溯源约定:凡对 hermes-agent 行为的断言,锚点写作 `路径:行号 @ 863e313`,
> **单独成行、置于代码块之前**;围栏块是逐字源码摘录。
> 基线 = `NousResearch/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`,只读。
> 命令一律以本学习仓库根(`/home/user/hermes-study`)为工作目录,可重跑。

---

## 0. 片清单与规模

本片 = R11A 的 L2 片 B,主题「这个产品怎么在 CI 里被验证、怎么在容器里被监督着跑起来」。

```verify
awk -F'\t' 'NR>1{sub(/\r$/,"",$2); n++; l+=$2} END{printf "%d 文件 / %d 行\n", n, l}' data/r11a/slices/slice-L2-B.tsv
```

```text
109 文件 / 21514 行
```

按目录拆开(五组,后面 §5 逐个点名):

```verify
awk -F'\t' 'NR>1{sub(/\r$/,"",$1); if($1 ~ /^\.github\/workflows\//) k="1 .github/workflows"; else if($1 ~ /^\.github\//) k="2 .github/ 其余"; else if($1 ~ /^docker\//) k="3 docker/"; else if($1 ~ /^scripts\/ci\//) k="4 scripts/ci/"; else k="5 scripts/ 其余"; c[k]++; s[k]+=$2} END{for(k in c) printf "%s\t%d 文件\t%d 行\n", k, c[k], s[k]}' data/r11a/slices/slice-L2-B.tsv | sort | sed 's/\t/ | /g'
```

```text
1 .github/workflows | 25 文件 | 3792 行
2 .github/ 其余 | 10 文件 | 757 行
3 docker/ | 18 文件 | 1164 行
4 scripts/ci/ | 9 文件 | 3352 行
5 scripts/ 其余 | 47 文件 | 12449 行
```

---

## 1. 这一片解决什么问题

三件事,彼此独立,只是恰好都不在产品代码里:

1. **一个 PR 该跑哪些检查、什么条件下阻断合并。** 难点不是「跑测试」,而是
   *「一个 8,530 文件的仓库,不能每个 PR 都跑全套」*。做法是把改动分类成 lane,
   由一个编排 workflow(`ci.yml`)按 lane 条件调用子 workflow,最后用**一个**聚合 job
   给分支保护当唯一必需检查。
2. **检查结果怎么回到人眼前。** 20 个 job 分散在十几个子 workflow 里,GitHub 原生的
   checks 列表读起来是一堵墙。这里自己造了一条**状态总线**:每个想露面的 job 产出一份
   `review_status` JSON、上传成 `review-status-*` 制品;一个常驻轮询 job 每 15 秒
   把它们汇成一条 PR 评论并原地更新。
3. **产物怎么在容器里被监督着跑。** 镜像用 **s6-overlay**(一个把 s6 进程监督套件打包成
   容器 init 的发行版:PID 1 是 `/init`,它按目录约定拉起「服务」并在崩溃时重启)。
   这一片是它的**镜像内脚本层**:`docker/cont-init.d/`(启动前一次性初始化)、
   `docker/s6-rc.d/`(服务定义)、以及几个把历史入口点接上新 init 的兼容 shim。

---

## 2. 接缝穷举

### 2.1 workflow 全表(25 个文件 / 61 个 job)

枚举脚本:`data/r11a/probes/probe_b_workflows.py`(只读解析 YAML,不执行任何 workflow;
注意 YAML 1.1 把裸 `on:` 解析成布尔 `True`,脚本两种键都认)。

```verify
python3 data/r11a/probes/probe_b_workflows.py /home/user/hermes-agent --count
```

```text
25 workflows / 61 jobs
```

逐项列全(不抽样),含各自触发器与 job 数:

```verify
python3 data/r11a/probes/probe_b_workflows.py /home/user/hermes-agent --brief | sed 's/\t/ | /g'
```

```text
file | name | triggers | n_jobs
ci.yml | CI | pull_request,push | 20
contributor-check.yml | Contributor Attribution Check | workflow_call | 1
deploy-site.yml | Deploy Site | release,push,workflow_dispatch | 2
docker-lint.yml | Docker / shell lint | workflow_call | 2
docker.yml | Docker Build, Test, and Publish | push,release,workflow_call | 3
docs-site-checks.yml | Docs Site Checks | workflow_call | 1
e2e-desktop.yml | E2E Desktop | workflow_call | 1
history-check.yml | History Check | workflow_call | 1
infographic-check.yml | Infographic Check | workflow_call | 1
install-e2e-run.yml | Install & Update E2E (reusable) | workflow_call | 1
install-e2e.yml | Install & Update E2E | workflow_dispatch,schedule,push | 3
installer-tests.yml | Installer tests | workflow_call | 1
js-autofix.yml | auto-fix lint issues & formatting | push,workflow_dispatch | 2
js-tests.yml | JS Tests | workflow_call | 2
label-rerun.yml | Label rerun | pull_request | 1
lint.yml | Lint (ruff + ty) | workflow_call | 3
lockfile-diff.yml | Lockfile diff | workflow_call | 1
osv-scanner.yml | OSV-Scanner | workflow_call,schedule,workflow_dispatch | 2
publish-e2e-evidence.yml | Publish E2E evidence | workflow_run | 1
review-labels.yml | Review labels | workflow_call | 1
skills-index-freshness.yml | Skills Index Freshness Check | schedule,workflow_dispatch | 1
skills-index.yml | Build Skills Index | schedule,workflow_dispatch,push | 2
supply-chain-audit.yml | Supply Chain Audit | workflow_call | 3
tests.yml | Tests | workflow_call | 4
uv-lockfile-check.yml | uv.lock check | workflow_call | 1
```

**读法。** 25 个里 **16 个只有 `workflow_call`** —— 它们不是独立入口,而是 `ci.yml` 的
子例程。真正的入口只有 9 个:

| 入口 | 触发 | 干什么 |
|---|---|---|
| `.github/workflows/ci.yml` | `pull_request` + push 到 main | 编排全部 PR 检查 |
| `.github/workflows/docker.yml` | push main / release published(**也**可被 `ci.yml` 调用) | 建镜像、跑容器集成测试、发布 |
| `.github/workflows/deploy-site.yml` | release / push(website、skills 路径)/ 手动 | 部署文档站与 Vercel |
| `.github/workflows/js-autofix.yml` | push main(JS/TS 路径)/ 手动 | 自动 `npm run fix` 并开 PR |
| `.github/workflows/label-rerun.yml` | PR 被打标签 | 打上 `ci-reviewed` 后重跑失败 job |
| `.github/workflows/install-e2e.yml` | 每 12 小时 / 发版 tag / 手动 | 真装真更新的端到端 |
| `.github/workflows/skills-index.yml` | 每天 6/18 点 / 手动 / 特定 push | 重建技能索引 |
| `.github/workflows/skills-index-freshness.yml` | 每 4 小时 / 手动 | 探活线上索引,劣化就开 issue |
| `.github/workflows/publish-e2e-evidence.yml` | `workflow_run`(CI 完成后) | 用可信身份把 E2E 截图贴回 PR |

`.github/workflows/osv-scanner.yml` 同时有 `workflow_call` 和 `schedule`,算半个入口
(既被 `ci.yml` 调,也每周一自己跑一次)。

### 2.2 `ci.yml` 的 20 个 job:各自的门条件

`.github/workflows/ci.yml:39-63 @ 863e313`

```yaml
  detect:
    name: Detect affected areas
    runs-on: ubuntu-latest
    timeout-minutes: 10
    outputs:
      python: ${{ steps.classify.outputs.python }}
      python_prod: ${{ steps.classify.outputs.python_prod }}
      frontend: ${{ steps.classify.outputs.frontend }}
      site: ${{ steps.classify.outputs.site }}
      scan: ${{ steps.classify.outputs.scan }}
      deps: ${{ steps.classify.outputs.deps }}
      npm_lock: ${{ steps.classify.outputs.npm_lock }}
      installer: ${{ steps.classify.outputs.installer }}
      docker_meta: ${{ steps.classify.outputs.docker_meta }}
      mcp_catalog: ${{ steps.classify.outputs.mcp_catalog }}
      ci_review: ${{ steps.classify.outputs.ci_review }}
      ci_review_files: ${{ steps.classify.outputs.ci_review_files }}
      event_name: ${{ github.event_name }}
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      - name: Detect affected areas
        id: classify
        uses: ./.github/actions/detect-changes
        with:
          github-token: ${{ github.token }}
```

全部 20 个 job(逐项,不抽样):

| job | 类型 | 触发条件(`if:`) |
|---|---|---|
| `detect` | 内联 | 无条件 |
| `tests` | 调 `tests.yml` | `python == 'true'`,传 `slice_count: 12` |
| `lint` | 调 `lint.yml` | `python == 'true'` |
| `js-tests` | 调 `js-tests.yml` | `frontend == 'true'` |
| `installer-tests` | 调 `installer-tests.yml` | `installer == 'true'` |
| `e2e-desktop` | 调 `e2e-desktop.yml` | **`false && (...)`——被硬关**(见 §4.1 ■-4) |
| `docs-site` | 调 `docs-site-checks.yml` | `site == 'true'` |
| `history-check` | 调 `history-check.yml` | `event_name == 'pull_request'` |
| `contributor-check` | 调 `contributor-check.yml` | `python == 'true'` |
| `uv-lockfile` | 调 `uv-lockfile-check.yml` | 无条件 |
| `infographic-check` | 调 `infographic-check.yml` | 无条件 |
| `lockfile-diff` | 调 `lockfile-diff.yml` | PR 且 `npm_lock == 'true'` |
| `docker-lint` | 调 `docker-lint.yml` | `docker_meta == 'true'` |
| `docker` | 调 `docker.yml` | PR 且(`python_prod` 或 `frontend` 或 `docker_meta`) |
| `supply-chain` | 调 `supply-chain-audit.yml` | PR 且(`scan` 或 `deps`) |
| `review-labels` | 调 `review-labels.yml` | `always()` 且 PR 且(`ci_review` 或 `mcp_catalog` 或 supply-chain 有 critical) |
| `osv-scanner` | 调 `osv-scanner.yml` | 无条件、**且不 `needs: detect`** |
| `comment-live` | 内联 | `always()` 且 PR 且非 fork |
| `all-checks-pass` | 内联 | `always()`——**分支保护唯一要求的检查** |
| `ci-timings` | 内联 | `always()`,`needs: [all-checks-pass, docker]` |

聚合门的 needs 列表逐字如下(注意末尾三行注释——**被排除的两个是有意的,第三个不是**):

`.github/workflows/ci.yml:242-263 @ 863e313`

```yaml
  all-checks-pass:
    name: All required checks pass
    needs:
      - detect
      - tests
      - lint
      - js-tests
      - installer-tests
      - e2e-desktop
      - docs-site
      - history-check
      - contributor-check
      - uv-lockfile
      - lockfile-diff
      - docker-lint
      - supply-chain
      - review-labels
      - osv-scanner
      # comment-live is a polling job — it doesn't block the gate.
      # we don't require docker to pass rn because it's so slow lol
      # - docker
    if: always()
```

机械求差(「`ci.yml` 里用 `uses:` 调子 workflow 的 job」减去「门的 needs」):

```verify
python3 data/r11a/probes/probe_b_workflows.py /home/user/hermes-agent --gate-gap
```

```text
called-but-not-in-gate: docker infographic-check
```

`docker` 有注释交代;`infographic-check` 没有——见 §4.1 ■-1。

### 2.3 lane 分类器:11 条 lane,失败朝「多跑」倒

`.github/actions/detect-changes/action.yml` 只做一件事:用 compare API 拿这个 PR 的改动
文件名,喂给一个纯 Python 分类器。

`.github/actions/detect-changes/action.yml:109-111 @ 863e313`

```bash
        echo "Changed files:"
        printf '%s\n' "${CHANGED:-(none)}"
        printf '%s\n' "${CHANGED:-}" | python3 scripts/ci/classify_changes.py
```

分类器的常量表就是 lane 的定义:

`scripts/ci/classify_changes.py:44-49 @ 863e313`

```python
_FRONTEND = ("ui-tui/", "web/", "apps/")  # TS typecheck-matrix packages
_ROOT_NPM = {"package.json", "package-lock.json"}  # shifts every package's tree
_DOCKER_META = ("docker/", ".hadolint.yml", "Dockerfile") # docker setup
_SITE = ("website/", "skills/", "optional-skills/")  # docs site + skill pages
# Prose/frontend trees that can't touch Python. skills/ is excluded on purpose.
_PY_SKIP = ("docs/", "website/") + _FRONTEND
```

11 条 lane 逐项(取自同文件的 `classify()` 返回字典):
`python` / `python_prod` / `docker_meta` / `frontend` / `site` / `scan` / `deps` /
`npm_lock` / `installer` / `mcp_catalog` / `ci_review`,外加一条非布尔输出
`ci_review_files`(JSON 数组,告诉标签门「哪几个 CI 敏感文件动了」)。

**失败朝「多跑」倒**是这个设计的核心不变量——空 diff 或任何 `.github/` 改动都把所有 lane
强制打开:

`scripts/ci/classify_changes.py:140-150 @ 863e313`

```python
    if not files or any(f.startswith(".github/") for f in files):
        ret["python"] = True
        ret["python_prod"] = True
        ret["docker_meta"] = True
        ret["frontend"] = True
        ret["site"] = True
        ret["scan"] = True
        ret["deps"] = True
        ret["npm_lock"] = True
        ret["installer"] = True
        ret["ci_review"] = True
```

注意 `mcp_catalog` **不**在这个强开列表里(源码里紧跟一行注释说明是故意的)。

`python` 与 `python_prod` 的分工值得单记:`python_prod` 是「`tests/` 之外的 Python 改动」,
用来给「跑成品」的 job(Desktop E2E 的后端、Docker 镜像)开门——只改测试的 PR 仍要跑
pytest,但不必重建 5GB 镜像。

`scripts/ci/classify_changes.py:87-96 @ 863e313`

```python
def _py_test_only(p: str) -> bool:
    """Is ``p`` inside the test suite (never shipped / imported by the product)?

    Product jobs (Desktop E2E's ``hermes serve`` backend, the Docker image)
    run installed code — nothing under ``tests/`` is packaged or importable
    there. scripts/run_tests.sh and run_tests_parallel.py are deliberately
    NOT test-only: they are runner infrastructure, and a bad edit there can
    mask real failures, so they stay conservative (python_prod=true).
    """
    return p.startswith("tests/")
```

### 2.4 `review_status` 状态总线:9 个生产者 + 1 个消费者

约定是**同一份 JSON 走两条路**:一路写 `$GITHUB_OUTPUT`(给同一次 workflow 里的下游 job),
一路写成文件 `review-status.json` 上传为 `review-status-<name>` 制品(给跨 workflow 的
轮询器)。文件里存的是 **GITHUB_OUTPUT 格式**(`review_status=<JSON>`),不是裸 JSON——
消费端专门剥这个前缀:

`scripts/ci/live_comment.py:357-368 @ 863e313`

```python
def _parse_status_file(status_file: Path) -> list[dict]:
    """Parse a review-status.json file in GITHUB_OUTPUT format."""
    try:
        content = status_file.read_text(encoding="utf-8").strip()
        if content.startswith("review_status="):
            content = content[len("review_status="):]
        statuses = json.loads(content)
        if isinstance(statuses, list):
            return statuses
    except (json.JSONDecodeError, OSError):
        pass
    return []
```

制品生产者逐项列全(9 个):

| 制品名 | 产它的 workflow | 内容 |
|---|---|---|
| `review-status-ci-timings` | `.github/workflows/ci.yml`(`ci-timings` job) | CI 耗时报告链接与回归 |
| `review-status-contributor-check` | `.github/workflows/contributor-check.yml` | 未映射的贡献者邮箱 |
| `review-status-e2e-desktop` | `.github/workflows/e2e-desktop.yml` | 截图/视觉 diff |
| `review-status-history-check` | `.github/workflows/history-check.yml` | 无共同祖先 |
| `review-status-lockfile-diff` | `.github/workflows/lockfile-diff.yml` | npm 锁文件语义 diff |
| `review-status-osv-scanner` | `.github/workflows/osv-scanner.yml` | 已知 CVE 数 |
| `review-status-review-labels` | `.github/workflows/review-labels.yml` | 缺 `ci-reviewed` 标签 |
| `review-status-supply-chain` | `.github/workflows/supply-chain-audit.yml` | 无上界依赖 |
| `review-status-uv-lockfile` | `.github/workflows/uv-lockfile-check.yml` | `uv.lock` 不同步 |

消费者只有一个:`ci.yml` 的 `comment-live` job,跑 `scripts/ci/live_comment.py`。
它每 15 秒把编排 run **与所有 `workflow_call` 子 run** 的 job 状态抓一遍,再把上面 9 类
制品下载解析合并,组装成一条带 `<!-- hermes-ci-review-bot -->` 标记的 PR 评论并原地 upsert。

`.github/workflows/ci.yml:227-230 @ 863e313`

```yaml
        run: |
          python3 scripts/ci/live_comment.py \
            --interval 15 \
            --timeout 2100
```

**声明了输出却没有制品的那一个是 `infographic-check`** ——见 §4.1 ■-1。

### 2.5 s6 服务全表

`docker/s6-rc.d/` 是 s6-rc(s6 的服务依赖管理器)的**源目录**,Dockerfile 整目录拷进镜像。
s6-rc 的目录约定:目录里有 `type` 文件 ⇒ 它是服务(`longrun` 常驻 / `oneshot` 一次性);
没有 `type` 但有 `contents.d/` ⇒ 它是 bundle(服务集合);`dependencies.d/` 下每个**空文件的
文件名**是一条依赖边;`contents.d/` 下每个空文件名是 bundle 成员。

枚举脚本:`data/r11a/probes/probe_b_s6.py`。

```verify
python3 data/r11a/probes/probe_b_s6.py /home/user/hermes-agent | sed 's/\t/ | /g'
```

```text
name | type | dependencies | contents | finish
dashboard | longrun | base | - | yes
main-hermes | longrun | base | - | no
user | (bundle) | - | dashboard,main-hermes | no
```

即:**2 个 longrun 服务 + 1 个 bundle**,两个服务都只依赖 s6-overlay 内建的 `base` bundle,
彼此之间**无依赖边**;`user` bundle 同时收纳两者(s6-overlay 启动时拉起 `user` bundle)。

`main-hermes` 是个刻意的**空槽**——容器的 CMD 并不由它跑:

`docker/s6-rc.d/main-hermes/run:23-27 @ 863e313`

```sh
# For now this service is a no-op: it sleeps forever, doing nothing.
# The dashboard runs as a real s6 service alongside it (see
# ../dashboard/run) and per-profile gateways register dynamically via
# /run/service/ at runtime (Phase 4).
exec sleep infinity
```

`dashboard` 则用「`run` 干净退出 + `finish` 返回 125」把「未启用」表达成 s6 的
**永久失败**状态,而不是让 supervise 无限重启:

`docker/s6-rc.d/dashboard/finish:19-30 @ 863e313`

```sh
case "${HERMES_DASHBOARD:-}" in
    1|true|TRUE|True|yes|YES|Yes)
        # Dashboard was enabled — let s6-supervise restart on crash by
        # exiting non-125. (Pass-through any sensible default.)
        exit 0
        ;;
    *)
        # Dashboard disabled — permanent-failure marker so s6-supervise
        # leaves the slot in 'down' state and s6-svstat reflects that.
        exit 125
        ;;
esac
```

除这 2 个静态服务外,还有一类**运行时注册**的服务:每个 profile 的 gateway 在
`/run/service/`(tmpfs)里动态建槽,容器重启后由 `docker/cont-init.d/02-reconcile-profiles`
调 `hermes_cli.container_boot` 重建。它们不在 `docker/s6-rc.d/` 里,所以上表查不到——
这是本片能给出的**完整静态服务面**,动态面属 `hermes_cli/` 片。

### 2.6 `scripts/run_tests_parallel.py` 的分片与并发口径

**并发(`-j`)。** 默认 = `HERMES_TEST_WORKERS` 或 `cpu_count()*2`:

`scripts/run_tests_parallel.py:683-687 @ 863e313`

```python
        "-j",
        "--jobs",
        type=int,
        default=int(os.environ.get("HERMES_TEST_WORKERS") or (os.cpu_count() or 4) * 2),
        help="Parallel worker count (default: $HERMES_TEST_WORKERS or cpu_count*2)",
```

**隔离粒度 = 文件。** 每个 `test_*.py` 起一个独立 `python -m pytest <file>` 子进程,
用信号量限并发;不用 xdist。

**发现面。** 默认根 `tests/`,并跳过三个需要外部服务的子树:

`scripts/run_tests_parallel.py:73 @ 863e313`

```python
_SKIP_PARTS = {"integration", "e2e", "docker"}
```

跳过是**可被显式覆盖**的:如果调用方把被跳目录本身当作根传进来(`run_tests.sh tests/docker/`),
该目录对应的 skip 词会从有效集合里减掉。

**每文件超时 300 秒、失败文件重跑 1 次。**

`scripts/run_tests_parallel.py:86-95 @ 863e313`

```python
_DEFAULT_FILE_TIMEOUT_SECONDS = 300.0

# One-shot retry of failing test FILES. A file that exits non-zero is re-run
# once in a fresh subprocess; if the re-run passes, the file counts as passed
# but is loudly reported as FLAKY so it gets fixed rather than hidden.
# Deterministic failures fail both attempts — a real regression can never be
# laundered into green by this (it would have to flake in our favor twice in
# a row on the same runner, which is exactly the definition of a flake).
# Set to 0 to disable (env: HERMES_TEST_FILE_RETRIES).
_DEFAULT_FILE_RETRIES = 1
```

**分片算法 = LPT(最长优先)。** 按缓存时长降序排,依次塞进当前累计最小的桶;
没有缓存时长的文件按 2.0 秒估:

`scripts/run_tests_parallel.py:585-595 @ 863e313`

```python
    default_dur = 2.0
    file_durs: List[Tuple[Path, float]] = []
    for f in files:
        rel = _format_file(f, repo_root)
        dur = durations.get(rel, default_dur)
        file_durs.append((f, dur))

    # Sort longest first (LPT).
    file_durs.sort(key=lambda x: x[1], reverse=True)

    # Greedy assignment: for each file, add it to the slice with the
```

**两种分片入口。** `--slice I/N`(1 起,本地/单 job 用)与 `--generate-slices N`
(CI 用:算一次分配、打印 matrix JSON、退出,不跑任何测试):

`scripts/run_tests_parallel.py:909-926 @ 863e313`

```python
    # --generate-slices: compute LPT distribution and emit JSON, then exit.
    if args.generate_slices is not None:
        durations = _load_durations(repo_root)
        slices = _compute_lpt_slices(
            files, args.generate_slices, durations, repo_root
        )
        matrix = {
            "slice": [
                {
                    "index": i + 1,
                    "files": ":".join(_format_file(f, repo_root) for f in bucket),
                }
                for i, bucket in enumerate(slices)
            ]
        }
        # Print to stdout so the CI step can capture it with $().
        print(json.dumps(matrix))
        return 0
```

CI 侧 matrix job 拿到的是**文件清单**(冒号分隔),用 `--files` 绕开发现逻辑,
所以 12 个 job 不会各自重跑一次 LPT。

**环境穿透面。** `scripts/run_tests.sh` 用 `env -i` 清空环境后**显式**放行一小撮变量;
运行器自己的 6 个旋钮必须在这份白名单里,否则对调用者是静默空操作:

`scripts/run_tests.sh:144-150 @ 863e313`

```bash
TEST_ENV=()
for _test_var in HERMES_TEST_IMAGE HERMES_TEST_WORKERS HERMES_TEST_PATHS \
  HERMES_TEST_FILE_TIMEOUT HERMES_TEST_FILE_RETRIES HERMES_TEST_SLICE; do
  if [ -n "${!_test_var:-}" ]; then
    TEST_ENV+=("$_test_var=${!_test_var}")
  fi
done
```

### 2.7 `scripts/whatsapp-bridge/` 的对外接口面

这是一个**独立 Node 进程**(Baileys 客户端),Python 侧的 WhatsApp 适配器通过本地 HTTP 调它。
接口面 = HTTP 路由 + 四个可导入模块的导出。

HTTP 路由逐项(10 条):

```verify
cd /home/user/hermes-agent && grep -o "^app\.\(get\|post\)('[^']*'" scripts/whatsapp-bridge/bridge.js
```

```text
app.get('/messages'
app.post('/send'
app.post('/edit'
app.post('/send-media'
app.post('/send-poll'
app.post('/send-location'
app.post('/typing'
app.post('/read'
app.get('/chat/:id'
app.get('/health'
```

模块导出面(供进程内 import,也是那 6 个 `*.test.mjs` 的被测面):

| 模块 | 导出 |
|---|---|
| `scripts/whatsapp-bridge/allowlist.js` | `normalizeWhatsAppIdentifier` / `parseAllowedUsers` / `expandWhatsAppIdentifiers` / `matchesAllowedUser` |
| `scripts/whatsapp-bridge/outbound_ids.js` | `createOutboundIdTracker` |
| `scripts/whatsapp-bridge/owner_message_gate.js` | `classifyOwnerMessageGate` |
| `scripts/whatsapp-bridge/bridge_helpers.js` | `MIME_MAP`、`normalizeWhatsAppId`、`getMessageContent`、`getContextInfo`、`createBoundedMessageStore`、`pollCreationMessageSecret`、`pollUpdateForAggregation`、`buildTextSendPayload`、`buildLocationPayload`、`appendMediaFailureNote`、`extractBridgeEvent`、`inferMediaType`、`inboundReadReceiptKeys`、`mediaPayloadForFile`、`buildPollPayload`、`pollCreationMessageFromPayload`、`createReconnectScheduler`、`createVersionResolver`(18 个) |

启动面(`package.json`):`node bridge.js --port <n> --session <dir>`,依赖
`@whiskeysockets/baileys 7.0.0-rc13`、`express ^4.21.0`、`qrcode-terminal`、`pino`,
并对 `protobufjs` 做了 `overrides` 收紧。

### 2.8 被钉住的外部动作与工具版本(供仿写时抄口径)

全部第三方 action **按完整 commit SHA 钉住**(供应链策略),且 `dependabot` 只对
`github-actions` 生态开启。`.github/dependabot.yml` 把理由写在文件头:pip/npm 的源依赖
用 `uv.lock` / `package-lock.json` 精确钉死,**不接受按周自动升 pin**,只接受 CVE 触发的
安全更新(在仓库设置里单开)。

常出现的钉子:`actions/checkout@de0fac2e…` (v6.0.2)、`astral-sh/setup-uv@fac544c0…` (8.2.0,
且在 5 处 workflow 里重复写了「不钉版本会每 job 去 raw.githubusercontent.com 取 manifest」
的事故注释)、`actions/setup-node@49933ea5…` + `node-version: 26` + `npm i -g npm@12`、
`hadolint/hadolint-action@54c9adba…`、`ludeeus/action-shellcheck@00cae500…`、
`google/osv-scanner-action/.github/workflows/osv-scanner-reusable.yml@9a498708…`。

`.github/actions/` 只有 4 个本地复合动作,实际被引用的是 3 个:

```verify
cd /home/user/hermes-agent && grep -rho "uses: \./\.github/actions/[a-z-]*" .github/ | sort | uniq -c
```

```text
      1 uses: ./.github/actions/detect-changes
      5 uses: ./.github/actions/get-app-token
     19 uses: ./.github/actions/retry
```

---

## 3. 端到端链(逐跳带锚点)

### 链 A:一个 PR 从触发到「门」与 PR 评论

1. **触发。** `.github/workflows/ci.yml` 的 `on:` 是 `pull_request:` 与 push 到 `main`;
   并发组按 ref,PR 事件才 cancel-in-progress。
2. **分类。** `detect` job 调本地复合动作 `.github/actions/detect-changes`,后者用
   `gh api repos/<repo>/compare/<base>...<head>` 取文件名(3 次重试,失败朝「全开」倒),
   管道喂给 `scripts/ci/classify_changes.py`,输出 11 个 `lane=true/false` 到 `$GITHUB_OUTPUT`。
   (逐字见 §2.3 的两个块。)
3. **扇出。** 15 个 `uses:` job 各自按 lane 条件调子 workflow。例如 Python 测试:

`.github/workflows/ci.yml:69-76 @ 863e313`

```yaml
  tests:
    name: Python tests
    needs: detect
    if: needs.detect.outputs.python == 'true'
    uses: ./.github/workflows/tests.yml
    with:
      slice_count: 12

```

4. **各子 workflow 产状态。** 以 `uv-lockfile-check.yml` 为例,失败时把一份带
   `how_to_fix` 的 JSON 同时写进 `$GITHUB_OUTPUT` 和 `review-status.json`:

`.github/workflows/uv-lockfile-check.yml:133-134 @ 863e313`

```bash
            echo "review_status=${review_status}" >> "$GITHUB_OUTPUT"
            echo "review_status=${review_status}" > review-status.json
```

5. **上传成制品。** 同 job 末尾 `actions/upload-artifact` 传 `review-status-uv-lockfile`,
   `retention-days: 1`、`continue-on-error: true`(制品服务抖动不许拖垮检查)。
6. **轮询汇总。** `comment-live` 跑 `scripts/ci/live_comment.py --interval 15 --timeout 2100`;
   它先取编排 run 的 job,再按 head SHA 找同一批 `workflow_call` 子 run 的 job:

`scripts/ci/live_comment.py:192-197 @ 863e313`

```python
    # Sub-workflow runs (workflow_call)
    sub_runs = _api_get_paginated(
        f"{API_BASE}/repos/{owner}/{repo_name}/actions/runs?head_sha={head_sha}&event=workflow_call&per_page=100",
        token, list_key="workflow_runs",
    )
    sub_runs = [r for r in sub_runs if r.get("created_at", "") >= created_at]

```

7. **落地成一条评论。** 下载全部 `review-status-*` 制品 → `_parse_status_file` 剥
   `review_status=` 前缀 → 交给 `scripts/ci/assemble_review_comment.py` 组装 → upsert 到 PR。
8. **门。** `all-checks-pass` 用 `toJSON(needs)` 把每个依赖的 result 摊平,只有 `failure`
   才失败(`skipped` 当成功),并把紧凑的 `{job: result}` 作为 `needs-json` 输出:

`.github/workflows/ci.yml:282-291 @ 863e313`

```python
          failed = [name for name, info in needs.items() if info['result'] == 'failure']
          for name, info in sorted(needs.items()):
              result = info['result']
              icon = '✅' if result in ('success', 'skipped') else '❌'
              print(f'{icon} {name}: {result}')
          if failed:
              print(f'::error::{len(failed)} job(s) failed: {\", \".join(failed)}')
              sys.exit(1)
          print('All checks passed (or were skipped)')
          "
```

9. **补救回路。** 维护者给 PR 打 `ci-reviewed` 标签 → `.github/workflows/label-rerun.yml`
   被 `pull_request: [labeled]` 触发 → 等 CI run 结束 → `gh run rerun --failed`,
   于是 `review-labels` 重跑并看见标签,`all-checks-pass` 与 `comment-live` 作为下游被连带重跑。

### 链 B:12 个测试分片是怎么算出来的

1. `ci.yml` 调 `tests.yml` 并传 `slice_count: 12`(逐字见链 A 第 3 跳)。
2. `generate` job 先恢复时长缓存(`actions/cache/restore`,key `test-durations`,
   靠 `restore-keys: test-durations-` 前缀回落——注释里写明「精确 key 永远命中不了」),
   然后:

`.github/workflows/tests.yml:42-46 @ 863e313`

```yaml
      - name: Generate test slices
        id: matrix
        run: |
          MATRIX=$(python3 scripts/run_tests_parallel.py --generate-slices ${{ inputs.slice_count }})
          echo "matrix=$MATRIX" >> "$GITHUB_OUTPUT"
```

3. 该命令输出 `{"slice": [{"index": 1, "files": "a.py:b.py:…"}, …]}`(逐字见 §2.6)。
   **本地实跑一次这一跳**(只读,不落盘):

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 python3 scripts/run_tests_parallel.py --generate-slices 12 2>/dev/null | python3 -c "import json,sys; m=json.load(sys.stdin); print('matrix key:', list(m)); print('slices:', len(m['slice'])); print('total files:', sum(len(s['files'].split(':')) for s in m['slice']))"
```

```text
matrix key: ['slice']
slices: 12
total files: 2630
```

4. `test` job 用 `matrix: ${{ fromJSON(needs.generate.outputs.matrix) }}` 展开成 12 个 job,
   `fail-fast: false`,每个执行:

`.github/workflows/tests.yml:130-132 @ 863e313`

```bash
        run: |
          source .venv/bin/activate
          scripts/run_tests.sh --files '${{ matrix.slice.files }}'
```

5. `scripts/run_tests.sh` 先预编译字节码,再 `env -i` 起干净环境跑
   `scripts/run_tests_parallel.py`:

`scripts/run_tests.sh:165-169 @ 863e313`

```bash
echo "▶ pre-compiling bytecode cache"
"$PYTHON" -m compileall -q -j 0 -- $(git ls-files '*.py') >/dev/null 2>&1 || true

echo "▶ launching test runner"
exec env -i \
```

6. 每个分片把自己的 `test_durations.json` 传成 `test-durations-slice-<i>` 制品
   (`continue-on-error: true`)。
7. `save-durations` job(**仅 main 分支且 test 全绿**)下载全部分片时长、合并、
   用 `key: test-durations-${{ github.run_id }}` 存回缓存——下一轮 `generate` 的
   `restore-keys` 前缀就命中它。这条回路闭合了 LPT 的输入。

### 链 C:容器从 `docker run` 到你的 CMD

1. **ENTRYPOINT。** 镜像的入口点不是 `hermes`,而是一个分派脚本:

`Dockerfile:456-457 @ 863e313`

```dockerfile
ENTRYPOINT [ "/opt/hermes/docker/entrypoint-dispatch.sh" ]
CMD [ ]
```

2. **分派。** 它按「自己是不是 PID 1」二选一:

`docker/entrypoint-dispatch.sh:15-24 @ 863e313`

```sh
set -e

if [ "$$" -eq 1 ]; then
    exec /init /opt/hermes/docker/main-wrapper.sh "$@"
fi

echo "[hermes] WARNING: container entrypoint is not PID 1; skipping s6-overlay /init and falling back to direct bootstrap. Supervised services are unavailable in this runtime, but the requested command will still run." >&2
# /init normally seeds PATH with s6's helpers; the non-PID-1 fallback skips it.
export PATH="/command:/package/admin/s6/command:${PATH}"
/opt/hermes/docker/stage2-hook.sh
```

3. **cont-init 三步(字典序)。** Dockerfile 把 `docker/stage2-hook.sh` 包成
   `/etc/cont-init.d/01-hermes-setup`,再拷两个脚本进去:

`Dockerfile:352-357 @ 863e313`

```dockerfile
RUN mkdir -p /etc/cont-init.d && \
    printf '#!/command/with-contenv sh\nexec /opt/hermes/docker/stage2-hook.sh\n' \
        > /etc/cont-init.d/01-hermes-setup && \
    chmod +x /etc/cont-init.d/01-hermes-setup
COPY --chmod=0755 docker/cont-init.d/015-supervise-perms /etc/cont-init.d/015-supervise-perms
COPY --chmod=0755 docker/cont-init.d/02-reconcile-profiles /etc/cont-init.d/02-reconcile-profiles
```

   - `01-hermes-setup` → `docker/stage2-hook.sh`:UID/GID 重映射(含 NAS 的 PUID/PGID 别名)、
     数据卷**定向** chown、docker.sock 组补齐、配置种子、schema 迁移、技能同步、
     发现 Chromium。
   - `015-supervise-perms` → 把静态 s6 服务的 `supervise/` 与 `event/` 目录 chown 给
     非特权 `hermes` 用户(否则 UID 10000 下 `s6-svstat`/`s6-svc` 全部 EACCES)。
   - `02-reconcile-profiles` → chown `/run/service` 与 svscan 控制 FIFO,再以 hermes 身份跑
     `python -m hermes_cli.container_boot`,重建 profile gateway 的动态服务槽。
4. **服务起来。** s6-rc 编译 `/etc/s6-overlay/s6-rc.d/`(即 `docker/s6-rc.d/`),
   拉起 `user` bundle → `dashboard` + `main-hermes`(见 §2.5)。
5. **CMD 走「main program」这条路,不是服务。** `/init` 把
   `docker/main-wrapper.sh` 当主程序执行,它先 rehydrate 环境、拒绝
   `--user <任意 uid>`、把 `HOME` 改回 `/opt/data`、激活 venv、恢复用户的 `-w` 工作目录,
   然后按三条规则路由参数:

`docker/main-wrapper.sh:81-91 @ 863e313`

```sh
if [ $# -eq 0 ]; then
    drop hermes
fi

if command -v "$1" >/dev/null 2>&1; then
    # Bare executable — pass through directly.
    drop "$@"
fi

# Hermes subcommand pass-through.
drop hermes "$@"
```

6. **`docker exec` 另有一条路。** `/opt/hermes/bin/hermes`(= `docker/hermes-exec-shim.sh`)
   排在 PATH 最前,root 执行时先 `s6-setuidgid hermes` 再 exec 真 venv 二进制,
   避免 `docker exec <c> hermes login` 把 `auth.json` 写成 root:root 从而让被监督进程读不到。
7. **历史入口的两个 shim。** `docker/entrypoint.sh`(老 ENTRYPOINT,现在只跑 stage2 并告警
   「不会 exec CMD」)与 `docker/tini-shim.sh`(装在 `/usr/bin/tini`,吃掉 tini 的
   `-g/-s/-w/-v/-p/-e/--` 等 flag 再转交 `/init` + main-wrapper,防止老编排模板把 `-g`
   传进 s6 导致 `rc.init: -g: not found` 的无限重启)。

---

## 4. 记号(■/▲/◇/◎)与负结论

### 4.1 ■ 代码缺陷

**■-1 `infographic-check` 不在合并门里,而它自称是「能强制执行的检查」。**
该 workflow 的文件头明确说 `.gitignore` 拦不住 `git add -f` 和拼错的目录名,「A passive
ignore rule cannot enforce a policy. This check can.」但 `ci.yml` 的 `all-checks-pass`
needs 列表里没有它(逐字见 §2.2 的块;机械求差见同节 `--gate-gap`,输出
`docker infographic-check`)。`docker` 有一行注释交代为什么排除,`infographic-check` **没有**。
后果:提交了信息图的 PR 会让 `infographic-check` 这个 job 红,但分支保护要求的唯一检查
`all-checks-pass` 仍然绿。

同一条缺陷还有第二面:它**声明了** `review_status` 输出,却从不把它写成
`review-status.json`,也就永远进不了 PR 评论那条状态总线(§2.4)。

```verify
cd /home/user/hermes-agent && printf 'infographic-check.yml 里写 review-status.json 的次数: '; grep -c "review-status.json" .github/workflows/infographic-check.yml; printf 'ci.yml 里提到 infographic-check 的行: '; grep -c "infographic-check" .github/workflows/ci.yml
```

```text
infographic-check.yml 里写 review-status.json 的次数: 0
ci.yml 里提到 infographic-check 的行: 2
```

(那 2 行就是 job 名和 `uses:` 两行,没有任何一行消费它的输出。)

**■-2 `docker_meta` lane 认的是 `.hadolint.yml`,而仓库里的文件叫 `.hadolint.yaml`。**
于是改 hadolint 规则文件**不会**打开 `docker_meta`,`docker-lint` job 不跑——而
`docker-lint.yml` 恰恰是唯一用这份配置的地方(`config: .hadolint.yaml`)。
lane 常量逐字见 §2.3 的第一个块。

```verify
cd /home/user/hermes-agent && ls -1 .hadolint.*; printf 'classify_changes.py 里 .hadolint.yml 出现次数: '; grep -c '\.hadolint\.yml' scripts/ci/classify_changes.py
```

```text
.hadolint.yaml
classify_changes.py 里 .hadolint.yml 出现次数: 1
```

注:`python` lane 因为「不认识的路径就保持开」而仍会打开,所以这不是「全都不跑」,
而是**恰好漏掉与该文件唯一相关的那个 job**。

**■-3 `label-rerun.yml` 的状态解析写坏了,快路径永远走不到。**
`RUN_ID` 先被截成纯数字,`STATUS` 再从**已截断的** `RUN_ID` 上取「最后一个空格之后」——
没有空格,于是 `STATUS` = 那串数字。

`.github/workflows/label-rerun.yml:54-58 @ 863e313`

```bash
          # Split "RUN_ID STATUS" into two vars.
          RUN_ID="${RUN_ID%% *}"
          STATUS="${RUN_ID##* }"

          echo "Latest CI run: $RUN_ID (status: $STATUS)"
```

复现(纯 shell,与 GitHub 无关):

```verify
RUN_ID="123456 completed"; RUN_ID="${RUN_ID%% *}"; STATUS="${RUN_ID##* }"; echo "RUN_ID=$RUN_ID STATUS=$STATUS"
```

```text
RUN_ID=123456 STATUS=123456
```

后果:`STATUS != "completed"` 恒成立,于是即便 run 已经结束也总是进
「等待完成」分支去跑 `gh run watch`,并且日志里那句 `(status: …)` 打印的是 run id。
实际危害有限(对已完成的 run,`gh run watch` 会立刻返回;之后还有一次
`gh run view --json status` 兜底),但这条分支的**存在理由**——「已完成就直接重跑」——
从未生效过。

**■-4 `e2e-desktop` 被 `false &&` 硬关,却仍留在门的 needs 与轮询器的 needs 里。**

`.github/workflows/ci.yml:106-114 @ 863e313`

```yaml
    # ⛔ TEMPORARILY DISABLED (Aug 2, 2026, Teknium) — the suite is red on
    # every PR and on main itself since the Aug 1 night engines/npm churn
    # (#76499 → #76562 → #76575): the mock-backend Electron window never
    # gets a title, so boot/chat/setup/interim specs all fail identically
    # regardless of the PR's diff (verified on #76573 and the docs-only
    # #76582). Tracking issue: #76627 (assigned: Ari). To re-enable,
    # delete the `false &&` below — nothing else changed.
    if: ${{ false && (needs.detect.outputs.python_prod == 'true' || needs.detect.outputs.frontend == 'true') }}
    uses: ./.github/workflows/e2e-desktop.yml
```

连带效应值得记:`publish-e2e-evidence.yml` 靠 `e2e-evidence-*` 制品工作,而只有
`e2e-desktop.yml` 产这个制品;于是那条「可信 `workflow_run` 发布器把截图贴回 PR」的
链路目前每次都走「没找到制品 → exit 0」。这不是缺陷,是**被关停功能的下游**,
但读代码的人很容易把它当成活的链路。

**■-5 `scripts/whatsapp-bridge/` 的 6 个 `*.test.mjs`(950 行)没有任何 CI 会跑。**
搜索面写清楚:(a) `.github/` 全树 grep `whatsapp`,只有 1 行命中,是
`osv-scanner.yml` 把它的 `package-lock.json` 列为扫描目标;(b) `.github/` 全树 grep
`node --test` 与 `test.mjs`,零命中;(c) 根 `package.json` 的 `workspaces` 不含
`scripts/whatsapp-bridge`,而 `js-tests.yml` 的矩阵是「遍历 npm workspaces 找 `check*` 脚本」;
(d) 该目录自己的 `package.json` 只有一个 `start` 脚本,没有 `check`/`test`;
(e) 全仓 grep 这 6 个测试文件名,除自身目录外零引用。

```verify
cd /home/user/hermes-agent && printf '.github/ 提到 whatsapp 的行数: '; grep -rn "whatsapp" .github/ | wc -l; printf '.github/ 提到 node --test 或 test.mjs 的行数: '; grep -rn "node --test\|test\.mjs" .github/ | wc -l; printf 'root workspaces: '; python3 -c "import json;print(json.load(open('package.json'))['workspaces'])"; printf 'bridge package.json scripts: '; python3 -c "import json;print(json.load(open('scripts/whatsapp-bridge/package.json'))['scripts'])"
```

```text
.github/ 提到 whatsapp 的行数: 1
.github/ 提到 node --test 或 test.mjs 的行数: 0
root workspaces: ['apps/*', 'ui-tui', 'ui-tui/packages/*', 'web', 'tests-js']
bridge package.json scripts: {'start': 'node bridge.js'}
```

这些不是玩具测试:`bridge.sendqueue.test.mjs` 的文件头写着它是 #33360
「并发 `/send` 造成跨聊天串台」的回归测试,`bridge.reconnect.test.mjs` 是
「重连楔死」的回归测试。回归测试不跑 = 回归会再来。

**■-6 `.github/actions/nix-setup/` 是死资产。** 全 `.github/` 树里 `uses:` 引用的本地
复合动作只有 3 个(枚举见 §2.8 的 `uniq -c`,`nix-setup` 零命中);把搜索面扩到全仓
(排除 `website/` 与 `.git/`)也找不到任何引用,`website/` 里的 `nix-setup` 全部是文档站
的一个页面路径 `/getting-started/nix-setup`,与这个 action 无关。

### 4.2 ▲ 文档所述与代码矛盾

**▲-1 `AGENTS.md` 说包装器把 `HOME` 换成每测试临时目录;代码明确说不换。**
该断言归哪个标题管(CLAUDE.md 要求一并判定):

`AGENTS.md:1312 @ 863e313`

> #### Why the wrapper

它管辖的那张对照表里的一格:

`AGENTS.md:1317 @ 863e313`

> | HOME / `~/.hermes/` | Your real config+auth.json                  | Temp dir per test                         |

代码侧两处都反着说。其一,`scripts/run_tests.sh` 的 `env -i` 白名单**原样转发真 HOME**:

`scripts/run_tests.sh:169-171 @ 863e313`

```bash
exec env -i \
  PATH="$PATH" \
  HOME="$HOME" \
```

其二,conftest 把「不改 HOME」写成了显式不变量:

`tests/conftest.py:8-12 @ 863e313`

```python
2. **Isolated HERMES_HOME.** HERMES_HOME points to a per-test tempdir so
   code reading ``~/.hermes/*`` via ``get_hermes_home()`` can't see the
   real one. (We do NOT also redirect HOME — that broke subprocesses in
   CI. Code using ``Path.home() / ".hermes"`` instead of the canonical
   ``get_hermes_home()`` is a bug to fix at the callsite.)
```

**整格判定**(按 CLAUDE.md「整句/整段一并判定」):这一格的**左标签把 HOME 与
`~/.hermes/` 并列**,右侧只给一个结论「Temp dir per test」。其中
`~/.hermes/` 那一半是**成立的**——只是靠 `HERMES_HOME` 重定向,不靠 HOME;
`HOME` 那一半**被代码明确否定**。所以这是 ▲,但它是「一格讲两件事、其中一件错」的形状,
读者按它去调试「为什么我的 `Path.home()` 代码在测试里读到了真 home」会被引到错误方向——
而 conftest 恰好把这种代码称作「a bug to fix at the callsite」。

**▲-2 `scripts/run_tests_parallel.py` 自己的模块 docstring 把默认并发写成 `os.cpu_count()`,
实现是 `cpu_count()*2`。** 这条严格说是**源码内**文档与实现不符(不是 README/AGENTS/website
那张「作者自绘地图」),但它同样会让读者算错本地并发量,故一并记在这里。

`scripts/run_tests_parallel.py:33-35 @ 863e313`

```
Environment:
    HERMES_TEST_WORKERS  Override worker count (default: os.cpu_count())
    HERMES_TEST_PATHS    Override discovery roots (colon-sep, default: 'tests')
```

实现见 §2.6 的 `-j` 块(`(os.cpu_count() or 4) * 2`);同一个 argparse 的 `help=`
字符串写的是 `cpu_count*2`,即**同一文件里两处自述互相矛盾**,只有 docstring 那处是错的。

### 4.3 ◇ 代码有、文档无

**◇-1 `review_status` 这条「结构化评审状态总线」在 `website/docs` 与 `AGENTS.md` 里没有说明。**
它有一份完整契约(`kind` ∈ `error|action_required|warning|info|debug`、
`title`/`summary`/`detail`/`how_to_fix`/`link`,以 `source` 去重),写在
`scripts/ci/assemble_review_comment.py` 的模块 docstring 里,而不是任何面向贡献者的文档。
搜索面:全仓 grep `review_status`,命中集中在 `.github/workflows/*.yml`(9 个)与
`scripts/ci/*.py`(4 个),`website/`、`AGENTS.md`、`CONTRIBUTING.md` 零命中。

**◇-2 「非 PID 1 也能起」这条容器兼容路径没有文档。** `docker/entrypoint-dispatch.sh`
为 Fly Machines / `docker run --init` / 部分 Nomad-K8s 场景准备了一条**跳过 s6 监督树**的
降级路径(逐字见链 C 第 2 跳),运行时会打一条 WARNING。这个「监督服务不可用但 CMD 照跑」
的降级语义只在脚本注释里。

### 4.4 ◎ 文档成立但显著保守

**◎-1 `scripts/whatsapp-bridge/bridge.js` 文件头列了 8 个端点,实际有 10 个**
(缺 `/send-poll` 与 `/read`,两者都被 `plugins/platforms/whatsapp/adapter.py` 真实调用)。
文件头同时把消费者写成 `gateway/platforms/whatsapp.py`,而基线里没有这个文件——
适配器已经搬到 `plugins/platforms/whatsapp/adapter.py`。端点全表见 §2.7。

```verify
cd /home/user/hermes-agent && printf 'bridge.js 实际路由数: '; grep -c "^app\.\(get\|post\)(" scripts/whatsapp-bridge/bridge.js; printf 'gateway/platforms/whatsapp.py 存在吗: '; test -f gateway/platforms/whatsapp.py && echo yes || echo no; printf 'adapter 里调 /send-poll 与 /read 的行数: '; grep -c "/send-poll\|/read\"" plugins/platforms/whatsapp/adapter.py
```

```text
bridge.js 实际路由数: 10
gateway/platforms/whatsapp.py 存在吗: no
adapter 里调 /send-poll 与 /read 的行数: 2
```

### 4.5 负结论(带搜索面)

三条全称否定,每条都把搜索面写出来。

**N-1:PR 事件跑不到任何仓库级凭据。** 搜索面 = `.github/workflows/ci.yml` 全文里
`secrets.*` 的引用集合,以及非注释行的 `secrets: inherit`。结果:编排器只引用内建的
`secrets.GITHUB_TOKEN`(GitHub 自动注入的、按 workflow `permissions:` 收敛的令牌),
没有任何 `secrets: inherit`。真正的凭据都在别处、且都挂了保护环境与事件条件:
`docker.yml` 的 `publish`/`merge`(`environment: container-publish`,`if:` 限 push-main 或 release)、
`deploy-site.yml` 的 `VERCEL_DEPLOY_HOOK`(`if:` 限 release/手动)、
`js-autofix.yml` 的 `apply-patch`(`environment: trusted-automation`,`push` 触发)、
`skills-index.yml` / `skills-index-freshness.yml`(`trusted-automation`,`schedule`/`dispatch`)、
`publish-e2e-evidence.yml`(`environment: gh-image`,`workflow_run`)。
**这是静态阅读结论,未做任何模拟运行。**

**N-2:`docker/` 下没有第二处会递归 chown 用户挂载卷根目录的代码。** 搜索面 =
`docker/` 全树中**非注释行**出现 `chown ` 的文件。三个命中都已逐行读过:
`stage2-hook.sh`(顶层只 chown 目录**本身**,只对固定 13 个子目录递归,且递归前有
`path_has_symlink_component` 拒绝符号链接路径)、`cont-init.d/015-supervise-perms`
(只碰 `/run/s6-rc/servicedirs/*/supervise` 与 `/event`)、`cont-init.d/02-reconcile-profiles`
(只碰 `/run/service` 与 svscan 的两个 FIFO)。另有两个文件在**注释**里提到 chown
(`docker/entrypoint.sh`、`docker/main-wrapper.sh`),不执行。

**N-3:`.github/` 下零处 `pull_request_target`。** 搜索面 = `.github/` 全树 grep 该字面量。
这与 N-1 的设计一致(该触发器会让 fork PR 的代码在有凭据的上下文里跑)。

```verify
cd /home/user/hermes-agent && printf 'N-1 ci.yml 非注释行的 "secrets: inherit": '; grep -cE '^[^#]*secrets: inherit' .github/workflows/ci.yml; printf 'N-1 ci.yml 引用到的 secrets: '; grep -o 'secrets\.[A-Z_]*' .github/workflows/ci.yml | sort -u | paste -sd' ' -; printf 'N-2 docker/ 下非注释行执行 chown 的文件: '; grep -rlE "^[^#]*chown " docker/ | sort | paste -sd' ' -; printf 'N-3 .github/ 里 pull_request_target 命中行数: '; grep -rn "pull_request_target" .github/ | wc -l
```

```text
N-1 ci.yml 非注释行的 "secrets: inherit": 0
N-1 ci.yml 引用到的 secrets: secrets.GITHUB_TOKEN
N-2 docker/ 下非注释行执行 chown 的文件: docker/cont-init.d/015-supervise-perms docker/cont-init.d/02-reconcile-profiles docker/stage2-hook.sh
N-3 .github/ 里 pull_request_target 命中行数: 0
```

---

## 5. 逐文件点名(109 个,全路径)

下面五张表把片内 109 个文件逐个点名(全路径 + 一句话角色)。机械复核:

```verify
python3 data/r11a/probes/probe_b_named_coverage.py data/r11a/slices/slice-L2-B.tsv notes/r11a-raw-ci-and-container.md
```

```text
片内文件 109  全路径零命中 0  裸文件名零命中 0
```

### 5.1 `.github/workflows/`(25 文件 / 3,792 行)

| 全路径 | 一句话角色 |
|---|---|
| `.github/workflows/ci.yml` | PR 编排器:跑一次 lane 分类,按 lane 调子 workflow,收敛到一个门 job |
| `.github/workflows/tests.yml` | Python 测试:LPT 生成 12 分片 + 跑分片 + 回存时长缓存 + 独立 e2e job |
| `.github/workflows/lint.yml` | ruff/ty 的三 job:PR 差分(咨询)、`ruff check .`(阻断)、Windows 陷阱扫描(阻断) |
| `.github/workflows/js-tests.yml` | 枚举 npm workspaces 的 `check*` 脚本生成矩阵并逐个跑 |
| `.github/workflows/installer-tests.yml` | Windows runner 上跑 `install.ps1` 的 PowerShell 测试(pwsh 7 与 5.1 各一遍) |
| `.github/workflows/e2e-desktop.yml` | Playwright + xvfb 的 Electron 视觉回归(当前被 `ci.yml` 硬关) |
| `.github/workflows/docs-site-checks.yml` | 重生成技能文档页 + 图表 lint + Docusaurus 构建 |
| `.github/workflows/history-check.yml` | 拒绝与 main 无共同祖先的 PR(#25045 事故的机制化) |
| `.github/workflows/contributor-check.yml` | 检查新提交的作者邮箱是否已在 `contributors/emails/` 映射 |
| `.github/workflows/infographic-check.yml` | 拒绝把 PR 信息图 PNG 提交进仓库(见 ■-1) |
| `.github/workflows/uv-lockfile-check.yml` | `uv lock --check`,针对 PR 的**合并态**校验锁文件 |
| `.github/workflows/lockfile-diff.yml` | npm 锁文件的**语义** diff(咨询,不阻断) |
| `.github/workflows/docker-lint.yml` | hadolint 扫 Dockerfile + shellcheck 扫 `docker/`(severity=error) |
| `.github/workflows/docker.yml` | amd64/arm64 双架构构建 + 容器集成测试 + 按 digest 发布 + manifest 合并 |
| `.github/workflows/supply-chain-audit.yml` | 窄口径恶意模式扫描(`.pth`、base64+exec、混淆 subprocess、安装钩子)+ 依赖上界检查 |
| `.github/workflows/osv-scanner.yml` | 对 5 个锁文件扫 OSV 漏洞库,SARIF 进 Security 页;不阻断 |
| `.github/workflows/review-labels.yml` | CI 敏感文件 / MCP 目录 / 供应链告警需要 `ci-reviewed` 标签,否则失败 |
| `.github/workflows/label-rerun.yml` | 打上 `ci-reviewed` 后自动重跑失败 job(见 ■-3) |
| `.github/workflows/publish-e2e-evidence.yml` | `workflow_run` 可信发布器:把 E2E 截图转成 GitHub 附件贴回 PR |
| `.github/workflows/js-autofix.yml` | main 上跑 `npm run fix`,两 job 拆权后经 bot 分支自动开 PR 并 auto-merge |
| `.github/workflows/deploy-site.yml` | 文档站部署(GitHub Pages)+ Vercel 钩子;含技能索引复用/回落逻辑 |
| `.github/workflows/skills-index.yml` | 每天两次重建统一技能索引,并触发文档站部署 |
| `.github/workflows/skills-index-freshness.yml` | 每 4 小时探活线上索引,超 26 小时或源塌缩就开/追评 watchdog issue |
| `.github/workflows/install-e2e.yml` | 定时/发版触发:挑若干历史 release tag,矩阵跑「装旧版→更新到本提交」 |
| `.github/workflows/install-e2e-run.yml` | 上者的可复用单腿:装 bubblewrap 等、放开 userns、跑 `tests/install/install-update-e2e.sh` |

### 5.2 `.github/` 其余(10 文件 / 757 行)

| 全路径 | 一句话角色 |
|---|---|
| `.github/actions/detect-changes/action.yml` | 复合动作:取 PR 改动文件 → 喂 `classify_changes.py` → 输出 11 条 lane |
| `.github/actions/retry/action.yml` | 复合动作:把命令经 env 传入(不插值)并重试 N 次,可捕获 stdout 为输出;全仓被用 19 次 |
| `.github/actions/get-app-token/action.yml` | 复合动作:用 GitHub App 换 1 小时安装令牌;无 client-id 时回落 `github.token` |
| `.github/actions/nix-setup/action.yml` | 复合动作:装 Nix + 配 Cachix;**当前零引用**(见 ■-6) |
| `.github/dependabot.yml` | 只对 `github-actions` 生态开 dependabot,每周一批量;源依赖 pin 只走 CVE 安全更新 |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR 模板:变更说明、关联 issue、变更类型勾选、测试与截图栏 |
| `.github/ISSUE_TEMPLATE/config.yml` | issue 入口配置:允许空白 issue,外链 Discord / README / CONTRIBUTING |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Bug 表单:强制先搜重复、先 `hermes update`、贴 `hermes debug share` 链接 |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | 特性表单:先问「这该不该是一个 skill 而不是内置工具」 |
| `.github/ISSUE_TEMPLATE/setup_help.yml` | 安装/配置求助表单,同样要求先贴 `hermes debug share` |

### 5.3 `docker/`(18 文件 / 1,164 行)

| 全路径 | 一句话角色 |
|---|---|
| `docker/stage2-hook.sh` | cont-init 主脚本(591 行):UID/GID 重映射、卷定向 chown、docker.sock 组、配置种子与 schema 迁移、技能同步、Chromium 发现 |
| `docker/entrypoint-dispatch.sh` | 镜像真 ENTRYPOINT:是 PID 1 就 `exec /init`,否则降级直跑 stage2 + main-wrapper |
| `docker/main-wrapper.sh` | `/init` 的「主程序」:环境 rehydrate、拒绝任意 `--user`、`HOME=/opt/data`、激活 venv、CMD 三路由 + 降权 |
| `docker/entrypoint.sh` | 已废弃的老 ENTRYPOINT shim:只跑 stage2 并告警「不会 exec CMD」 |
| `docker/tini-shim.sh` | 装成 `/usr/bin/tini`,吃掉 tini 的 flag 再转 `/init`,防老编排模板把 `-g` 塞进 s6 导致重启风暴 |
| `docker/hermes-exec-shim.sh` | 装成 `/opt/hermes/bin/hermes`,`docker exec` 以 root 进来时先降权,避免写出 root 属主的 `auth.json` |
| `docker/cont-init.d/015-supervise-perms` | 把静态 s6 服务的 `supervise/`、`event/` chown 给 hermes,否则 UID 10000 下所有 s6 控制命令 EACCES |
| `docker/cont-init.d/02-reconcile-profiles` | chown `/run/service` 与 svscan FIFO,再跑 `hermes_cli.container_boot` 重建 profile 服务槽 |
| `docker/s6-rc.d/main-hermes/run` | 空槽服务:`exec sleep infinity`,只为让 `user` bundle 非空并预留未来常驻进程 |
| `docker/s6-rc.d/main-hermes/type` | 内容为 `longrun` |
| `docker/s6-rc.d/main-hermes/dependencies.d/base` | 空文件 = 依赖 s6-overlay 的 `base` bundle |
| `docker/s6-rc.d/dashboard/run` | dashboard 服务:未启用则 exit 0;启用则 `HOME=/opt/data` + 激活 venv + 降权跑 `hermes dashboard` |
| `docker/s6-rc.d/dashboard/finish` | 未启用时返回 125(s6 的「永久失败,别重启」),让 `s6-svstat` 如实报 down |
| `docker/s6-rc.d/dashboard/type` | 内容为 `longrun` |
| `docker/s6-rc.d/dashboard/dependencies.d/base` | 空文件 = 依赖 `base` bundle |
| `docker/s6-rc.d/user/contents.d/dashboard` | 空文件 = `user` bundle 收纳 dashboard |
| `docker/s6-rc.d/user/contents.d/main-hermes` | 空文件 = `user` bundle 收纳 main-hermes |
| `docker/SOUL.md` | 单行默认人格提示词,由 `stage2-hook.sh` 首启时种进 `$HERMES_HOME/SOUL.md` |

`docker/SOUL.md` 的种子点:

`docker/stage2-hook.sh:432 @ 863e313`

```sh
seed_one "SOUL.md" "docker/SOUL.md"
```

### 5.4 `scripts/ci/`(9 文件 / 3,352 行)

| 全路径 | 一句话角色 |
|---|---|
| `scripts/ci/classify_changes.py` | 纯函数 lane 分类器:读 stdin 的改动路径,写 11 条 `lane=bool` + `ci_review_files` |
| `scripts/ci/live_comment.py` | 轮询器:抓编排 run + 子 run 的 job 状态、下载合并 `review-status-*` 制品、upsert 一条 PR 评论 |
| `scripts/ci/assemble_review_comment.py` | 把 `{job: result}` 与 `review_status` 数组渲染成 Markdown 评论(带 bot 标记) |
| `scripts/ci/emit_review_status.py` | 为 `review-labels` 生成 0~3 条状态项(有标签给 `info`,没标签给 `action_required` + 核查清单) |
| `scripts/ci/timings_report.py` | 从 Actions API 收集 job/step 耗时,产 HTML gantt 报告 + 与 main 基线的 diff + 步骤摘要 |
| `scripts/ci/lockfile_diff.py` | 解析 lockfileVersion 2/3 的 `packages` 映射,做 `{路径: 版本}` 集合 diff,输出 Markdown 片段 |
| `scripts/ci/e2e_screenshot_status.py` | 从 Playwright `test-results/` 里挑「显式截图」,产清单 + 证据目录 + 评审状态 |
| `scripts/ci/publish_e2e_evidence.py` | 可信发布器:校验清单与 PNG 字节(签名、≤20 文件、≤5MB/文件、≤20MB 总量)后传成 GitHub 附件并替换评论占位符 |
| `scripts/ci/test_install_ps1_path_migration.ps1` | 从 `install.ps1` 的 AST 里提出 PATH 迁移函数、只重写两处注册表调用后真跑;**不接在默认 CI 通道上** |

### 5.5 `scripts/` 其余(47 文件 / 12,449 行)

**测试编排(2)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/run_tests.sh` | 唯一权威测试入口:探测 venv(要求真有 pytest)、`env -i` 清环境、预编译字节码、转交并行器 |
| `scripts/run_tests_parallel.py` | 每文件一子进程的并行 pytest 运行器:发现、LPT 分片、超时、文件级重试、FLAKY 报告、时长缓存 |

**静态守卫与 lint(3)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/check-windows-footguns.py` | grep 式规则集:`os.kill(pid,0)`、`os.setsid`、无 `encoding=` 的 `open()` 等 Windows 陷阱 |
| `scripts/check_subprocess_stdin.py` | 检查 TUI 上下文代码里的 `subprocess.run/Popen` 是否显式给了 `stdin=`(防 gateway 因 stdin EOF 退出) |
| `scripts/lint_diff.py` | 把 base/head 两侧的 ruff+ty 报告按 (文件, 规则, 行) 稳定键做差,产 Markdown 摘要 |

**贡献者与发布配套(3)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/add_contributor.py` | 在 `contributors/emails/` 下按邮箱写一个文件(避免改 `release.py` 的冻结 AUTHOR_MAP 引发冲突) |
| `scripts/audit_pr_attribution.py` | 本地复刻 `contributor-check.yml` 的判定,`--fix` 可自动补映射文件 |
| `scripts/contributor_audit.py` | 交叉比对 git 作者、`Co-authored-by` 尾注、被 salvage 的 PR 描述,找发布说明里漏掉的人 |

**沙箱与安装 E2E 支撑(5)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/sandbox/stage2-run.sh` | dev-sandbox 第二阶段:在已建好的 user/net namespace 里用 bwrap 搭挂载并跑 payload |
| `scripts/sandbox/proxy.py` | 假互联网 MITM 代理:命中 fixture 就本地作答(用来喂真 `curl \| bash` 一行安装),否则转发真上游 |
| `scripts/sandbox/openssl.cnf` | 沙箱替换掉 `/etc` 后 openssl 找不到配置,用这份最小配置供签发临时证书 |
| `scripts/sandbox/ssh-shim.sh` | 假 `ssh`:忽略参数直接对沙箱内裸仓库跑 upload-pack,让 `git@github.com:` 这条路无密钥可测 |
| `scripts/sandbox/pick-release-tags.sh` | 运行时挑「最新 + 最旧 + 中间等距」的 release tag,输出 JSON 数组给 Actions 矩阵 |

**运维诊断(7)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/discord-voice-doctor.py` | 逐项检查 Discord 语音所需依赖、配置与 bot 权限 |
| `scripts/keystroke_diagnostic.py` | 打印 prompt_toolkit 在当前终端下把按键识别成什么(加键位绑定前用,Windows 尤甚) |
| `scripts/iso-certify.py` | AC-4 隔离认证台:起隔离 dashboard,6 路重负载 agent turn 下验证 p99<1s 且事件循环不停顿 |
| `scripts/profile-tui.py` | 在 `HERMES_DEV_PERF` 下驱动 TUI(按住 PageUp)并汇总 `perf.log` 流水线耗时 |
| `scripts/micro_compaction_report.py` | 汇总 micro-compaction 遥测 JSON 行,报「这个特性到底省了多少」 |
| `scripts/observability/otel_capture_collector.py` | 极简本地 OTLP/HTTP 采集器:收 traces/metrics/logs 记成 JSONL 并回 200 |
| `scripts/observability/gateway_health_export_probe.py` | 对着上面那个采集器跑一遍 Gateway 健康与诊断导出 |

**基准与实验(11)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/LIVETEST_README.md` | Tool Search 实测台的说明:跑法、需要 `OPENROUTER_API_KEY`、验证了什么 |
| `scripts/tool_search_livetest.py` | v1:注册 ~20 个仿 MCP 工具,对真模型跑 5 场景 × 开/关两模式,记全量 transcript |
| `scripts/tool_search_livetest2.py` | v2:包一层 OpenAI client 记真实 token 用量,每场景多次重复 |
| `scripts/tool_search_livetest_ue.py` | v3:回放 Epic UE 5.8 真实的 830 个工具 schema,比较 eager/bridge/listing 三模式 |
| `scripts/tool_search_livetest_ue_hard.py` | v4:针对同名近义工具簇构造对抗场景,消除 v3 的天花板效应 |
| `scripts/tool_search_livetest_ue_disc.py` | v5:发现受限任务(BM25 敌对改写、以及「根本没有这个工具」的缺席判定) |
| `scripts/analyze_livetest.py` | 读上面产出的 `_summary.json` 并排比对开/关两组,标异常 |
| `scripts/benchmark_browser_eval.py` | 对同一个真 Chrome 比较「子进程 eval」与「supervisor-WS eval」两条路径 |
| `scripts/toolperf_abeval/ab_eval.py` | 核心工具集改动的硬 A/B:两臂只差 `PYTHONPATH`,按 NeMo Relay ATOF 轨迹打分 |
| `scripts/toolperf_abeval/run_all.sh` | 上者的批量驱动:N 模型 × 2 臂 × 9 任务 × R 重复 |
| `scripts/toolperf_abeval/README.md` | 该 A/B 台的设计说明(两臂一变量、任务即陷阱、指标口径) |

**杂项工具(4)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/sample_and_compress.py` | 从多个 HuggingFace 数据集抽样轨迹并跑压缩到目标 token 预算 |
| `scripts/smoke_nemo_relay_shared_metrics.py` | 跑一次真 CLI turn 并校验 Relay 共享指标输出 |
| `scripts/kill_modal.sh` | 批量停 Modal 上的 sandbox/部署 app |
| `scripts/capture-cage-terminal.sh` | 在 `cage --` 里用 grim 抓隔离 Wayland 显示上的终端截图 |

**WhatsApp bridge(12)**

| 全路径 | 一句话角色 |
|---|---|
| `scripts/whatsapp-bridge/bridge.js` | 主进程:Baileys socket + Express,10 条 HTTP 路由(见 §2.7) |
| `scripts/whatsapp-bridge/bridge_helpers.js` | 18 个纯函数/工厂:载荷构造、事件抽取、投票聚合、重连调度、有界消息存储 |
| `scripts/whatsapp-bridge/allowlist.js` | 发送方白名单:标识符归一、解析、按会话目录展开别名、匹配 |
| `scripts/whatsapp-bridge/outbound_ids.js` | 有界集合,记住自己发出去的消息 id(用于识别回环) |
| `scripts/whatsapp-bridge/owner_message_gate.js` | 判定「机主自己发的消息」该放行还是忽略 |
| `scripts/whatsapp-bridge/package.json` | 私有包定义:`start` 脚本、Baileys/express/pino 依赖、`protobufjs` overrides |
| `scripts/whatsapp-bridge/bridge.native.test.mjs` | 原生载荷助手的单测(刻意不 import `bridge.js`,因为它一加载就起服务) |
| `scripts/whatsapp-bridge/bridge.reconnect.test.mjs` | 重连楔死的回归测试(`fetchLatestBaileysVersion` 无 AbortSignal 导致永久断连) |
| `scripts/whatsapp-bridge/bridge.sendqueue.test.mjs` | #33360 回归:并发 `/send` 必须串行化,否则跨聊天串台 |
| `scripts/whatsapp-bridge/allowlist.test.mjs` | 白名单展开与匹配的单测(带临时会话目录) |
| `scripts/whatsapp-bridge/outbound_ids.test.mjs` | 出站 id 追踪器的单测 |
| `scripts/whatsapp-bridge/owner_message_gate.test.mjs` | 机主消息门的单测 |

> 上表 6 个 `*.test.mjs` 合计 950 行,**当前没有任何 CI 会跑**——见 ■-5。

---

## 6. 待提供项(不自行解决,按铁律记录)

| 缺什么 | 卡住了什么 | 备注 |
|---|---|---|
| GitHub Actions 运行环境(或 `act`) | 25 个 workflow 一个都没实跑过,§2 的接缝表是**静态解析**结论 | `act` 未安装,本轮不装 |
| `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | `docker.yml` 的 `publish`/`merge` 无法验证 | 属 `container-publish` 保护环境 |
| `vars.APP_CLIENT_ID` / `secrets.APP_PRIVATE_KEY` | `get-app-token` 的非回落分支、`js-autofix` 的 apply、`skills-index*` 全链 | 属 `trusted-automation` 保护环境 |
| `VERCEL_DEPLOY_HOOK`、`GH_IMAGE_SESSION_TOKEN` | `deploy-site` 的 Vercel 腿、`publish-e2e-evidence` 的附件上传 | |
| docker daemon | 无法构建镜像、无法验证链 C 的任何一跳(s6 启动顺序、cont-init 三步、CMD 路由) | CLI 在、socket 不在 |
| `shellcheck` / `hadolint` | 无法本地复现 `docker-lint.yml` 两个 job | |
| `npm install`(被本轮铁律禁止) | `scripts/whatsapp-bridge/` 的 6 个 `*.test.mjs` 无法运行 | `node_modules` 不存在;**未安装、未运行** |

```verify
test -S /var/run/docker.sock && echo "docker daemon socket: present" || echo "docker daemon socket: absent"; for b in shellcheck hadolint act; do printf '%s: ' "$b"; command -v "$b" >/dev/null && echo present || echo absent; done; test -d /home/user/hermes-agent/scripts/whatsapp-bridge/node_modules && echo "bridge node_modules: present" || echo "bridge node_modules: absent"
```

```text
docker daemon socket: absent
shellcheck: absent
hadolint: absent
act: absent
bridge node_modules: absent
```

---

## 7. 移交项(锚点 + 紧跟摘录 + 一句话现象)

| 编号 | 锚点与摘录 | 现象 / 下一轮该做什么 |
|---|---|---|
| H-R11A-B-a | `.github/workflows/ci.yml:262` 的 `# - docker` | 门 job 的 needs 排除了 `docker` **有**注释、排除 `infographic-check` **没有**注释;需要判定后者是遗漏还是有意,判定前不要在成品章里把 infographic 说成「阻断」 |
| H-R11A-B-b | `scripts/ci/classify_changes.py:46`:`_DOCKER_META = ("docker/", ".hadolint.yml", "Dockerfile") # docker setup` | 常量写 `.hadolint.yml`,仓库文件是 `.hadolint.yaml`;改这个配置不会触发 `docker-lint`。下一轮若做「配置键面」可把这类「常量里的文件名 vs 真实文件名」做成一次全仓机械核对 |
| H-R11A-B-c | `.github/workflows/label-rerun.yml:56`:`STATUS="${RUN_ID##* }"` | 从已截断的变量上取后缀,`STATUS` 恒等于 run id;「已完成就直接重跑」的快路径从未生效 |
| H-R11A-B-d | `scripts/whatsapp-bridge/bridge.sendqueue.test.mjs:2` 的 `Regression tests for the WhatsApp bridge send queue (#33360).` | 该目录 6 个 `*.test.mjs` 无 CI 覆盖(搜索面见 ■-5);若后续轮次要盘「测试即行为规格」,这批是**有规格但无执行**的一类,别按「已被 CI 保证」记 |
| H-R11A-B-e | `.github/actions/nix-setup/action.yml:16` 的 `name: hermes-agent` | 该复合动作零引用;A 片(Nix 打包)可能持有它被摘除的上下文,两片结论应合并判定 |
| H-R11A-B-f | `scripts/run_tests_parallel.py:33` 的 `HERMES_TEST_WORKERS  Override worker count (default: os.cpu_count())` | 同一文件的 docstring 与 argparse `help=` 对默认并发口径互相矛盾(实现是 `*2`);报测试数时若要复算并发,以实现为准 |
| H-R11A-B-g | `.github/workflows/ci.yml:113` 的 `if: ${{ false && (needs.detect.outputs.python_prod == 'true'` | Desktop E2E 全线关停,导致 `publish-e2e-evidence.yml`、`scripts/ci/e2e_screenshot_status.py`、`scripts/ci/publish_e2e_evidence.py` 三处**代码活着但链路死着**;写成品章时须标明这是当前状态而非设计 |
