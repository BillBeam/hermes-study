# r11a-92 · 主线复核(不采信自报,逐条重跑)

> 制度要求主线复核子代理的条目。本卷记录**主线自己跑的那一遍**:关卡数字全部重跑,
> 各片的实质结论抽样独立取证——**用与子代理不同的方法**,否则复核只是把同一条命令跑两次。
> 溯源约定:`路径:行号 @ 863e313`。

## 1. 关卡数字:自报 vs 主线重跑

| 片 | 指标 | 子代理自报 | 主线重跑 | 一致 |
|---|---|---|---|---|
| B | citations / OK / 可校验比例 | 35 / 35 / 100.0% | 35 / 35 / 100.0% | ✅ |
| B | table_anchors / OK | 7 / 7 | 7 / 7 | ✅ |
| B | paired / unpaired / differing | 17 / 0 / 0 | 17 / 0 / 0 | ✅ |
| B | 点名 全路径 / 裸名 零命中 | 0 / 0 | 0 / 0 | ✅ |
| C | citations / OK / 可校验比例 | 51 / 39 / 76.5% | 51 / 39 / 76.5% | ✅ |
| C | table_anchors / OK | 16 / 16 | 16 / 16 | ✅ |
| C | paired / unpaired / differing | 9 / 0 / 0 | 9 / 0 / 0 | ✅ |
| C | 点名 全路径 / 裸名 零命中 | 0 / 0 | 0 / 0 | ✅ |

**无一夸大。** 两片都没有出现 R10B 那种"自报关卡数与重跑对不上"的情况。

---

## 2. 片 B 的四条实质复核

### 2.1 ■-1 合并门漏掉 `infographic-check` —— 成立,但**两个口径要分开报**

片 B 的口径是「`ci.yml` 里用 `uses:` 调子 workflow 的 job」减「门的 needs」。
主线换了方法:直接 YAML 解析,拿**全部** job 求差。

```verify
cd /home/user/hermes-agent && /home/user/hermes-venv/bin/python -c "
import yaml
d=yaml.safe_load(open('.github/workflows/ci.yml',encoding='utf-8')); j=d['jobs']
g='all-checks-pass'; n=set(j[g].get('needs') or [])
u={k for k,v in j.items() if isinstance(v,dict) and 'uses' in v}
print('jobs',len(j),'uses-jobs',len(u),'gate-needs',len(n))
print('uses 口径缺口 :',sorted(u-n-{g}))
print('全 job 口径缺口:',sorted(set(j)-n-{g}))"
```

```text
jobs 20 uses-jobs 16 gate-needs 15
uses 口径缺口 : ['docker', 'infographic-check']
全 job 口径缺口: ['ci-timings', 'comment-live', 'docker', 'infographic-check']
```

两个读数**不是矛盾,是两个总体**:多出来的 `ci-timings` / `comment-live` 不带 `uses:`,
是内联的报告型 job。片 B 的结论(`infographic-check` 未入门、且无注释交代)成立。
**按制度,这两个数分别标注,不写成"读数相同"。**

### 2.2 ■-2 hadolint 配置文件名对不上 —— 成立

`scripts/ci/classify_changes.py:46 @ 863e313`

```
_DOCKER_META = ("docker/", ".hadolint.yml", "Dockerfile") # docker setup
```

而仓库里的文件叫 `.hadolint.yaml`,且**唯一**消费它的 workflow 也写 `.yaml`:

`.github/workflows/docker-lint.yml:36 @ 863e313`

```
          config: .hadolint.yaml
```

```verify
cd /home/user/hermes-agent && ls -a | grep -c '^\.hadolint\.yaml$'
```

```text
1
```

后果:改 hadolint 规则不会被分到 `docker` lane,于是 `docker-lint` 不跑。

### 2.3 ■-6 `nix-setup` composite action 零引用 —— 成立,**但主线第一次搜错了搜索面**

主线首次搜 `grep -rn "nix-setup" .`,得 **17 处命中**,差点判成"有人用"。
那 17 处全是 `website/docs/getting-started/nix-setup` 这个**同名文档页**,
与 `.github/actions/nix-setup` 毫无关系。正确的搜索面是「composite action 的引用写法」:

```verify
cd /home/user/hermes-agent && grep -rho "uses: \./\.github/actions/[a-z-]*" .github/ | sort | uniq -c | sort -rn
```

```text
     19 uses: ./.github/actions/retry
      5 uses: ./.github/actions/get-app-token
      1 uses: ./.github/actions/detect-changes
```

四个 composite action 里,`nix-setup` 一次都没出现。
*这条记在这里是因为它演示了负结论的成本:**同一个否定,换个搜索面就从"证伪"变回"成立"**。*

### 2.4 ▲-1 `AGENTS.md` 的 HOME 那一格 —— 成立,且片 B 的**整格判定**做对了

文档那一格把两件事并列:

`AGENTS.md:1317 @ 863e313`

> | HOME / `~/.hermes/` | Your real config+auth.json                  | Temp dir per test                         |

后半(`~/.hermes/`)成立;前半(`HOME`)被两处代码否定——包装器把**真** HOME 转发进去:

`scripts/run_tests.sh:171 @ 863e313`

```
  HOME="$HOME" \
```

而 conftest 明写不重定向 HOME:

`tests/conftest.py:10 @ 863e313`

> real one. (We do NOT also redirect HOME — that broke subprocesses in

按 CLAUDE.md「判定一条文档断言必须把整句/整格一并判定」,这一格**半真半假**,记 ▲ 正确。

---

## 3. 片 C 的三条实质复核

### 3.1 ■-1 `skills/apple/DESCRIPTION.md` 被静默丢弃 —— 成立,分母也对

```verify
cd /home/user/hermes-agent && printf 'DESCRIPTION.md under skills/: '; find skills -name DESCRIPTION.md | wc -l; printf 'without YAML front-matter : '; for f in $(find skills -name DESCRIPTION.md); do head -1 "$f" | grep -q '^---' || echo "$f"; done | wc -l
```

```text
DESCRIPTION.md under skills/: 16
without YAML front-matter : 1
```

16 份里 15 份有 front-matter,唯一没有的就是 `skills/apple/DESCRIPTION.md`。丢弃点:

`agent/prompt_builder.py:1741 @ 863e313`

```
                if not cat_desc:
```

*注意分母口径*:只数**顶层** `skills/*/DESCRIPTION.md` 是 **12** 份,数**全部**(含嵌套)是 **16** 份。
片 C 用的是后者(它说"其余 15 个"),与本复核一致。**两个数都记下来,不合并。**

### 3.2 ■-2 作者本机路径随货发出 —— 成立,9 文件 18 处逐项复现

```verify
cd /home/user/hermes-agent && printf 'files: '; grep -rl '/home/bb/hermes-agent' . | wc -l; printf 'occurrences: '; grep -rn '/home/bb/hermes-agent' . | wc -l; printf 'shipped SKILL.md among them: '; grep -rl '/home/bb/hermes-agent' --include=SKILL.md . | wc -l
```

```text
files: 9
occurrences: 18
shipped SKILL.md among them: 3
```

3 份是**随 `sync_skills()` 发到每个用户**的 `SKILL.md`,其余 6 份是文档站页面
(3 份英文 + 3 份中文译本)。

### 3.3 ◇-1 契约测试的不对称 —— 成立(主线换了搜索面复核)

`optional-mcps/` 的清单有仓库级**扫全量**的契约测试:

`tests/hermes_cli/test_mcp_catalog.py:560 @ 863e313`

> """Every manifest in optional-mcps/ must parse cleanly.

而 183 份 shipped `SKILL.md` 没有同形态的扫全量测试。**搜索面**:`tests/` 下
`SKILL.md` 字面命中 508 处,但那些都是**逐个技能**的单点测试;
按"是否有人 glob 全量"这个形状去搜,零命中:

```verify
cd /home/user/hermes-agent && printf 'shipped SKILL.md: '; find skills optional-skills -name SKILL.md | wc -l; printf 'tests globbing ALL of them: '; grep -rnE 'r?glob\(.*SKILL\.md|"\*\*/SKILL\.md"' tests/ --include=*.py | wc -l
```

```text
shipped SKILL.md: 183
tests globbing ALL of them: 0
```

*这条同样是搜索面问题:只搜 `SKILL.md` 会得到 508 处命中、看起来覆盖充分;
要搜的是"有没有人扫全量"。*

---

## 4. 基线洁净:两个读数,都要报

制度的检查是 `git status --porcelain` 为空,本轮全程为 **0**。但那只覆盖**被跟踪**的文件。
主线为 H-R8D-j 跑过一次全量 pytest 收集,它在基线里留下了被 `.gitignore` 覆盖的产物:

```verify
cd /home/user/hermes-agent && printf 'tracked porcelain : '; git status --porcelain | wc -l; printf 'incl. ignored     : '; git status --porcelain --ignored | wc -l; printf 'tracked diff lines: '; git diff HEAD --stat | wc -l
```

```text
tracked porcelain : 0
incl. ignored     : 248
tracked diff lines: 0
```

**引用基准没有被动过**(`路径:行号 @ 863e313` 仍然有效,tracked diff 为 0),
但"porcelain 为 0"**不等于**"什么都没写进去"。两个读数分别报,不写成一个。
