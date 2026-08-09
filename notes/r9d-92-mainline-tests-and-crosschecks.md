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

**无整文件静默跳过**:全日志无 `skipped` / `importorskip` / `no tests ran`。
(R9C 的 E 片曾因 `pytest.importorskip` 整文件不跑而"全绿",本轮范围内没有这种形态。)

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
