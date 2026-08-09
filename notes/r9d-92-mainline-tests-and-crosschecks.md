# r9d-92 · 主线合并测试 与 三条跨轮复核

> 主线产出。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 本篇装三件主线自己做的事:(1) 一次**合并去重**的全量测试(不是各片读数求和);
> (2) 用本轮范围内的 `agent/file_safety.py` 复核 R9C 的 `op_cache` 定案;
> (3) `hermes_cli/secrets_cli.py` 落盘面与禁读清单的对读(结清 H-R9C-b 的核心问号)。

---

## 1. 主线合并全量测试(一次测量,不是求和)

R9C 报告 §8 明写它的测试合计是「各片自报读数之和,主线没有另跑一次去重的合并全量,
故片间若有重复文件会被重复计入。**这是一个求和,不是一次测量**」。
本轮主线补上这次测量。

### 1.1 测试文件是怎么选的(可重跑)

不按文件名猜,按**是否 import 本轮的模块**选——名字相近但不测本轮代码的文件会被排除,
名字不像但确实 import 的会被收进来:

```verify
cd /home/user/hermes-agent && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5=="R9D") print $1}' \
    /home/user/hermes-study/data/ledger.tsv \
  | sed 's/\.py$//; s/\/__init__$//; s/\//./g' | grep -vE '^(agent|tools)$' | sort -u \
  | while read -r m; do esc=${m//./\\.}; \
      grep -rlE "(from[[:space:]]+${esc}[[:space:]]+import|import[[:space:]]+${esc}([[:space:]]|,|$))" \
        tests --include=test_*.py 2>/dev/null; \
    done | sort -u | wc -l
```

```text
133
```

**两个裸包名 `agent` 与 `tools` 被排除**(它们来自本轮的两个 `__init__.py`):
不排除的话 `from agent.任意模块 import` 会全部命中,一次实测得 1,107 个文件,
**那不是"覆盖本轮"而是"覆盖半个仓库"**。这两个 `__init__.py` 的覆盖改由 F 片逐文件交代。

### 1.2 读数

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
    HERMES_PYTHON=/home/user/hermes-venv/bin/python \
    bash scripts/run_tests.sh $(cat /tmp/r9d_tests3.txt | tr '\n' ' ')
```

```text
=== Summary: 133 files, 1829 tests passed, 2 failed (100% complete) in 71.8s (8 workers) ===
```

**133 文件 / 1,829 passed / 2 failed / 71.8 秒 / 8 worker。**
这是**一次合并去重的测量**;各片自报读数之和是另一个口径,两者**不可混报**(见报告 §8)。

**跳过情况(本节初稿判错,已撤回重判——留痕见下)**:

| 文件 | skipped | 原因 | 性质 |
|---|---|---|---|
| `tests/tools/test_send_message_tool.py` | **1(掩盖 47 个 `def test_`)** | `python-telegram-bot not installed` | **整文件跳过**,环境限制 |
| `tests/tools/test_signal_media.py` | 3 | httpx 类型注解与 telegram 库不兼容 | 环境限制 |
| `tests/tools/test_read_extract.py` | 3 | `firecrawl-anydoc not installed` | 环境限制 |
| `tests/agent/test_secret_scope_tier1_migration.py` | 2 | `azure-identity not installed` | 环境限制 |
| `tests/hermes_cli/test_web_server.py` | 1 | SQLite 3.45.1 的 WAL-reset bug,故无 `-wal` 边车可断言 | 环境限制 |
| `tests/run_agent/test_tool_batch_segmentation.py` | 1 | `normcase()` 大小写折叠只在 Windows 上有意义 | 正常的平台门控 |
| **合计** | **11** | | |

**最重的一条**:`tests/tools/test_send_message_tool.py` 是 D 片主文件
(`tools/send_message_tool.py`,2,116 行)的主测试,**47 个 `def test_` 一个都没跑**,
而运行器那一行显示的是 `✓ tests/tools/test_send_message_tool.py (1s, 1.1s)`。
`pytest.importorskip` 在模块级只记 **1 个 skip**,于是 47 个用例的缺失被压成一个字符。

**本节初稿的错判,及它是怎么发生的(留痕,不静默改写)**:
初稿写的是「**无整文件静默跳过**:全日志无 `skipped` / `importorskip` / `no tests ran`」。
**这是错的。** 依据是我对全日志 `grep -E "skipped|importorskip|no tests ran"` 得零命中——
但**运行器把 "skipped" 缩写成了 `s`**(`(1s, 1.1s)` 里的 `1s` 是"1 个跳过",不是"1 秒"),
所以那次 grep 的搜索面根本没覆盖到它。

*这正是 CLAUDE.md「负结论的成本」那条规矩描述的形状:**全称否定的可信度等于一次 grep 的完备性**,
而我那次 grep 不完备。它没被更早发现,是因为负结论**不会被下一个读者撞见**——
撞见它的是 D 片子代理在自己那一亩地里报了一条我"证明"过不存在的东西。*

正确的判定方法(逐文件解析运行器的括号读数,而不是搜关键词):

```verify
grep -oE "✓ tests/[^ ]+ \([^)]*\)" /tmp/r9d_mainline_tests.log \
  | grep -E "[0-9]+s," | sed 's/^✓ //'
```

### 1.3 两条失败的逐条诊断:是本项目自己的开工纪律造成的

两条都在 `tests/tools/test_web_tools_config.py::TestParallelClientConfig`:

```text
FAILED tests/tools/test_web_tools_config.py::TestParallelClientConfig::test_creates_client_with_key
FAILED tests/tools/test_web_tools_config.py::TestParallelClientConfig::test_singleton_returns_same_instance

E  ImportError: Feature 'search.parallel' unavailable: lazy installs disabled
   (security.allow_lazy_installs=false). To enable manually:
   uv pip install 'parallel-web==0.4.2'  (or: pip install 'parallel-web==0.4.2').
```

**报错自己点名了原因**:`security.allow_lazy_installs=false` —— 正是本轮(沿用 R9C)
开工时设的 `HERMES_DISABLE_LAZY_INSTALLS=1`。**非代码缺陷,也不是通常意义的容器限制,
而是本学习项目自己的纪律带来的。**

**这一条反过来是个有价值的测量。** 不设那个开关时,跑这个测试文件会**联网 pip 安装
`parallel-web==0.4.2` 到共享 venv**——即 R8A 立下"必须记 venv 包数"那条规矩要防的漂移,
也是 R9B 记的 H-R9B-g(「一个『读代码』的动作可以产生网络副作用并改变自身运行环境」)。
本轮把它从**静默的环境变更**变成了**一条可见的测试失败**。

佐证:跑完全量测试后该包**确实没被装上**,venv 两种数法都仍是 87。

```verify
/home/user/hermes-venv/bin/pip show parallel-web 2>&1 | head -1; \
/home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l; \
ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l
```

```text
WARNING: Package(s) not found: parallel-web
87
87
```

**我没有去掉开关重跑一次来"确认"**——那正好会装上这个包、把 venv 从 87 改成 88。
判定依据是报错原文点名的开关,以及该包确实缺失这一事实。**这是一处有意不做的验证,如实记在这里。**

### 1.4 CLAUDE.md 已知的 6 条必然失败用例

本轮范围内**一条都没碰到**(那 6 条分别属 `tests/hermes_cli/` 与 `tests/gateway/` 的
双栈绑定、root 运行、systemd、models.dev 目录、SQLite 措辞,均不在这 133 个文件里)。

---

## 2. 复核 R9C 的 `op_cache` 定案(用本轮范围内的文件)

R9C §6.2 第 8 条主线复核记:「`bws_cache` 出现在 **4 个守卫点**,`op_cache` 出现在 **0 个**」。
`agent/file_safety.py` **正在本轮的 49 个文件里**,所以本轮可以从被守卫的那一侧独立复核。

### 2.1 被守卫的一侧:Bitwarden 的两个缓存都在清单里

`agent/file_safety.py:49-51 @ 863e313`

```python
            # Bitwarden Secrets Manager encrypted disk cache.
            str(hermes_home / "cache" / "bws_cache.enc.json"),
            str(hermes_root / "cache" / "bws_cache.enc.json"),
```

明文那一份单独还有一处,**注释里记着这次疏漏本身**:

`agent/file_safety.py:281-284 @ 863e313`

```python
        # Bitwarden Secrets Manager disk cache: stores plaintext secret values
        # to avoid re-fetching across back-to-back CLI invocations. The file
        # was introduced by #31968 but not added to this guard.
        os.path.join("cache", "bws_cache.json"),
```

**"was introduced by #31968 but not added to this guard"** —— 仓库自己记下了
"新增了一个明文密钥缓存却忘了加进守卫"这件事发生过一次。

### 2.2 没被守卫的一侧:1Password 的缓存,而且是明文

`agent/secret_sources/onepassword.py:118 @ 863e313`

```python
_DISK_CACHE_BASENAME = "op_cache.json"
```

它用的是各后端共享的 `DiskCache`,该类**不加密**,只做原子写 + `chmod 0600`:

`agent/secret_sources/_cache.py:197-200 @ 863e313`

```python
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
                os.chmod(tmp, 0o600)
                os.replace(tmp, path)
```

`0600` 挡的是**别的 OS 用户**;而 agent 就跑在文件属主身份下,
**挡 agent 的那一层正是 `file_safety` 的禁读清单**——`op_cache.json` 不在其中。

### 2.3 主线的守卫点普查(口径写清楚,与 R9C 的数分别标注)

搜索面 = 基线全部非测试 `.py`;**"守卫点"定义为:出现在某个禁读/禁写清单里的那一行**
(把定义处、注释、临时文件前缀排除在外)。

```verify
cd /home/user/hermes-agent && grep -rn "bws_cache" --include=*.py . | grep -v "^./tests/"
```

```text
./gateway/platforms/base.py:1369:        os.path.join("cache", "bws_cache.json"),
./gateway/platforms/base.py:1370:        os.path.join("cache", "bws_cache.enc.json"),
./agent/secret_sources/bitwarden.py:95:# <hermes_home>/cache/bws_cache.json. The file holds only the secret VALUES,
./agent/secret_sources/bitwarden.py:100:_DISK_CACHE_BASENAME = "bws_cache.json"
./agent/secret_sources/bitwarden.py:101:_ENCRYPTED_CACHE_BASENAME = "bws_cache.enc.json"
./agent/secret_sources/bitwarden.py:425:            prefix=".bws_cache_enc_", suffix=".tmp", dir=str(cache_dir)
./agent/file_safety.py:50:            str(hermes_home / "cache" / "bws_cache.enc.json"),
./agent/file_safety.py:51:            str(hermes_root / "cache" / "bws_cache.enc.json"),
./agent/file_safety.py:284:        os.path.join("cache", "bws_cache.json"),
./hermes_cli/web_server.py:1779:    "bws_cache.json",
./hermes_cli/web_server.py:1780:    "bws_cache.enc.json",
```

```verify
cd /home/user/hermes-agent && grep -rn "op_cache" --include=*.py . | grep -v "^./tests/"
```

```text
./agent/secret_sources/onepassword.py:34:are cached in-process and on disk under ``<hermes_home>/cache/op_cache.json``
./agent/secret_sources/onepassword.py:118:_DISK_CACHE_BASENAME = "op_cache.json"
```

第三个守卫文件用的是**裸文件名**写法(前两个用 `os.path.join` 拼相对路径):

`hermes_cli/web_server.py:1779-1780 @ 863e313`

```python
    "bws_cache.json",
    "bws_cache.enc.json",
```

`gateway/platforms/base.py:1368-1370 @ 863e313`

```python
        # Bitwarden Secrets Manager plaintext and encrypted disk caches.
        os.path.join("cache", "bws_cache.json"),
        os.path.join("cache", "bws_cache.enc.json"),
```

按上面的定义逐条归类:

| 类别 | 处数 | 位置 |
|---|---|---|
| **守卫点(在禁读/禁写清单里)** | **7** | `gateway/platforms/base.py:1369`:`os.path.join("cache", "bws_cache.json"),`、`:1370`;`agent/file_safety.py:50`:`str(hermes_home / "cache" / "bws_cache.enc.json"),`、`:51`、`:284`;`hermes_cli/web_server.py:1779`:`"bws_cache.json",`、`:1780` |
| 定义 / 注释 / 临时前缀(非守卫) | 4 | `agent/secret_sources/bitwarden.py:95`:`# <hermes_home>/cache/bws_cache.json. The file holds only the secret VALUES,`、`:100`、`:101`、`:425` |
| **`op_cache` 的守卫点** | **0** | 仅 `agent/secret_sources/onepassword.py:118`:`_DISK_CACHE_BASENAME = "op_cache.json"` 与 `:34` 的文档串 |

**口径必须分别标注(不得说成"读数相同")**:R9C 报的是 **4 个守卫点**,本轮按上面这个定义数得
**7 处**(分布在 **3 个文件**)。**两者是不同定义下的两次测量,不是同一读数**——
R9C 未写出它的计数定义,故无法判断差在哪;本轮把定义写出来,便于以后复核。
**两次测量在结论上一致:`op_cache` 侧为 0。**

### 2.4 结论

**■ 成立(独立复核,与 R9C 同向)**:1Password 的**明文**密钥缓存
`<hermes_home>/cache/op_cache.json` 不在任何禁读清单里,而同类的 Bitwarden 缓存在 3 个文件里
共 7 处被挡。仓库自己在 `file_safety.py:283` 记着"上次就是这样漏的"。

**未取证**:未实跑一次 agent 的 `read_file` 去读 `op_cache.json` 观察是否放行——
那需要构造一个完整的工具执行上下文。本条是**静态清单对读**,证据等级为静态。

---

## 3. H-R9C-b 的核心问号:凭据落盘处在不在禁读清单里

R9C 移交 H-R9C-b 时给的现象是「真正的『凭据落盘那一侧』在 `hermes_cli/secrets_cli.py`
(token 写 `.env`),本轮只按需读了两处」。派工时我把它的关键问题定为:
**落到 `.env` 的凭据,agent 自己读不读得到?**

落盘目标(该文件多处自述):

`hermes_cli/secrets_cli.py:59 @ 863e313`

```python
        help="Provide the access token non-interactively (will be stored in .env)",
```

禁读清单这一侧,**两条路径都盖到了**:

`agent/file_safety.py:39-43 @ 863e313`

```python
            # Active profile .env (or top-level .env when not in profile mode).
            str(hermes_home / ".env"),
            # Top-level .env, even when running under a profile — overwriting it
            # leaks credentials across every profile that inherits from root (#15981).
            str(hermes_root / ".env"),
```

项目本地的 `.env` 家族另有一张基名表:

`agent/file_safety.py:183-191 @ 863e313`

```python
_BLOCKED_PROJECT_ENV_BASENAMES: set[str] = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".env.staging",
    ".envrc",
}
```

**结论:这个问号是阴性的——落盘目标在清单里,盖住了。**
这与 §2 的 `op_cache` 形成对照:**同一张清单,`.env` 这条主路径盖得很密
(profile 级 + 根级 + 项目本地七个基名),而后加的密钥缓存漏了一个。**
不是"没人管",是**"新增来源没有跟着更新清单"**——与 `file_safety.py:283` 那条注释所记的
是同一种失效方式。

*(H-R9C-b 的完整结构级理解见子代理取证书 `notes/r9d-90-handover-credential-landing.md`;
本节只做主线自己关心的这一个判定。)*

---

## 4. 主线复核子代理的最强断言(不照抄,实跑重验)

各片交付时附了 `strongest_claims` 与可重跑的复核方法。主线从中挑**最强、最反直觉、
一旦错就会污染成品章**的三条实跑重验。**三条全部复现。**

### 4.1 B 片 · 原子写的 `trap` 清理从不生效(与同函数 docstring 相反)

`tools/file_operations.py:1071 @ 863e313`

```python
            "trap 'rm -f \\\"$tmp\\\"' EXIT; "
```

同一函数的 docstring 承诺:

`tools/file_operations.py:1006-1008 @ 863e313`

```python
        On any failure the temp file is removed so we never leak a partial
        ``.hermes-tmp`` file next to the user's data, and the original file
        is left untouched. Content rides stdin so there is no ARG_MAX limit.
```

**病因**:shell 单引号内的 `\"` 是**字面量反斜杠加引号**,不是转义。trap 体在触发时被求值为
`rm -f \"$tmp\"`,参数于是变成**带字面双引号的文件名**,与真实临时文件名不符,`rm` 删不掉。

复核**不手抄源码**,直接从基线取那一行求值,再跑两组对照:

```verify
cd /home/user/hermes-agent && python3 -c "
import ast, pathlib
line = pathlib.Path('tools/file_operations.py').read_text().splitlines()[1070]
print('求值后:', repr(ast.literal_eval(line.strip().rstrip(','))))"
```

```text
求值后: 'trap \'rm -f \\"$tmp\\"\' EXIT; '
```

```verify
SP=/tmp/r9dprobe && mkdir -p $SP && rm -f $SP/tstA.* $SP/tstB.*
bash -c "set -e; tmp=$SP/tstA.\$\$; : > \"\$tmp\"; trap 'rm -f \\\"\$tmp\\\"' EXIT; false" 2>/dev/null
ls $SP/tstA.* 2>/dev/null || echo "基线写法:无残留"
bash -c "set -e; tmp=$SP/tstB.\$\$; : > \"\$tmp\"; trap \"rm -f '\$tmp'\" EXIT; false" 2>/dev/null
ls $SP/tstB.* 2>/dev/null || echo "正确写法:无残留"
```

```text
/tmp/r9dprobe/tstA.17504
正确写法:无残留
```

**基线写法残留、正确写法不残留。断言成立。**

### 4.2 B 片 · `write_file` 能覆盖 `auth.json`,而文档说它 always blocked

文档侧(注意归属标题是 `### Protected paths (always blocked)`,在 `security.md:281`):

`website/docs/user-guide/security.md:288 @ 863e313`

> | Hermes credential stores | `auth.json`, `.env`, `.anthropic_oauth.json`, `mcp-tokens/`, `pairing/` under HERMES_HOME (active profile and global root) |

代码侧,把该行**五个条目逐个**喂给写禁判据:

```text
文档所列条目                   is_write_denied    判定
auth.json                False              **没挡住**
.env                     True               挡住
.anthropic_oauth.json    True               挡住
mcp-tokens/              True               挡住
pairing/                 True               挡住
```

**五个里唯独 `auth.json` 没挡住,而它恰恰是主凭据库。** 端到端实证(临时 HERMES_HOME,不碰真环境):

```text
写入前: {"providers": {"nous": {"access_token": "REAL-SECRET-TOKEN"}}}
write_file_tool 返回: {"bytes_written": 12, "dirs_created": true, "verified": true,
                      "lint": {"status": "ok", ...}, "files_modified": [".../hh/auth.json"]}
写入后: {"pwned": 1}
```

**工具返回 `verified: true`、无 error,凭据库被整体覆盖。**
这一条同时是 **■**(agent 可摧毁用户凭据库)与 **▲**(文档在 "always blocked" 标题下点名了它)。
子代理断言成立,主线独立复现。

### 4.3 A 片 · LSP 工作区根会逃出 git 工作树

`agent/lsp/servers.py:205-209 @ 863e313`

```python
    found = nearest_root(
        file_path,
        markers,
        excludes=excludes,
        ceiling=os.path.dirname(workspace) if workspace else None,
    )
```

`ceiling` 传的是 `dirname(workspace)`(**工作树的父目录**),而 `nearest_root` 在 ceiling
那一层是**先查 marker、后判停**,于是工作树父目录里的 `pyproject.toml` 会被当成项目根。

```text
git 工作树      : /tmp/lsp-mtl8vndc/outer/repo
_root_python 返回: /tmp/lsp-mtl8vndc/outer
逃出工作树了吗   : 是 —— 工作区根在 git 工作树之外
```

**断言成立。** 其意义在于:git 闸门的全部目的就是把 LSP 的活动范围锁在工作树内,
而这个差一层让它在"父目录恰好也是个 Python 项目"时失效——
这在 monorepo 与 `~/projects/pyproject.toml` 这类布局下并不罕见。

### 4.4 B 片 · `patch` 完全绕过读禁清单,把明文密钥交给模型

这是 B 片自评「最强的一条」,主线独立复现。写侧判定装了,**读侧一步没有**:

`tools/file_operations.py:1674-1680 @ 863e313`

```python
        # Block writes to sensitive paths
        denied = get_write_denied_error(path)
        if denied:
            return PatchResult(error=denied)

        # Read current content
        read_cmd = f"cat {self._escape_shell_arg(path)} 2>/dev/null"
```

`get_write_denied_error` 之后紧跟的是**无条件 `cat`** —— 没有对应的 `get_read_denied_error`。
旧内容读出来后与新内容做成 unified diff 返回给模型,中间不经脱敏。

主线实跑(临时 HERMES_HOME,假密钥):

```text
read_file  -> {"error": "Access denied: <HH>/auth.json is a Hermes credential store and
               cannot be read directly. Provider tools consu...

patch      -> error: None | success keys: ['success', 'diff', 'files_modified', 'lint', 'resolved_path']

--- patch 返回给模型的 diff ---
--- a/<HH>/auth.json
+++ b/<HH>/auth.json
@@ -1,4 +1,4 @@
 {
-  "openai": {"api_key": "sk-SECRET-OPENAI-123"},
+  "openai2": {"api_key": "sk-SECRET-OPENAI-123"},
   "anthropic": {"api_key": "sk-ant-SECRET-456"}
 }

密钥是否原样出现在 diff 里: True / True
```

**同一个文件,`read_file` 判「拒绝」,`patch` 判「成功」并把两个密钥逐字交给模型。**
读禁清单是仓库对外声明的一条控制(拒绝语里还写了替代做法),`patch` 把它整条绕过去了。
断言成立,且与 §4.2 是同一个文件上的两个独立缺口(§4.2 是可写,本条是可读)。

### 4.5 复核结论

**抽验四条,四条全部复现,无一需要下调强度。** 四条分属两片、四种性质
(shell 引号错误 / 文档-代码矛盾 / 路径边界差一层 / 守卫只装在一条路径上),
覆盖面上算是有代表性的抽样;但**抽验不是全验**——各片其余断言以其底稿自证为准,
主线未逐条重跑,如实记在这里。
