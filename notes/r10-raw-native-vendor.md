# r10-native-vendor —— `native/fts5_cjk/vendor/` 两个 SQLite 随附头文件的处置

> 片名:**I · native/fts5_cjk 随附头文件(处置)**。片内 2 文件 / 14,498 行。
> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块之前。
> 本片的交付形态是**一次有依据的处置**,不是精读 14,498 行 C 头文件;篇幅短是设计,不是欠账。
>
> **术语一次性锚定**(读者假定不熟 SQLite C 生态):
> - **FTS5** = SQLite 内建的全文检索引擎(Full-Text Search v5),以「虚拟表」形式提供。
> - **分词器 / tokenizer** = FTS5 把一段文本切成可检索 token 的插件点。
> - **CJK** = 中日韩(Chinese/Japanese/Korean)文字。
> - **bigram(双字)** = 把连续 CJK 串切成两两重叠的字对,`캘린더` → `캘린` `린더`。
> - **可加载扩展 / loadable extension** = 编译成 `.so` 的动态库,由 SQLite 连接在运行时
>   `load_extension()` 装入;它拿到宿主库递给它的一张函数指针表,而不是静态链接进宿主。
> - **amalgamation(合并发行版)** = SQLite 官方把全部 C 源码合成 `sqlite3.c` + `sqlite3.h`
>   两个文件的发行形态;它的 `sqlite3.h` 末尾**追加**了 `fts5.h` 的内容。
> - **vendored(随附)** = 把第三方源码原样复制进本仓库、随仓库一起发布,不走包管理器。

---

## §1 这一片是什么

`native/fts5_cjk/` 是 hermes-agent 里唯一的 C 代码目录,产物是一个 FTS5 分词器
`cjk_unicode61`。本片只管它的 `vendor/` 子目录 —— 两个从 SQLite 官方拷来的头文件。
分词器本体(`fts5_cjk.c` / `build.sh` / `README.md`)**不在本片范围**,R5 已按结构级读过。

这两个头文件之所以存在于一个 Python 项目里,原因是一条很短的因果链:
`fts5_cjk.c` 要编译,就必须 `#include <sqlite3ext.h>`;而 `sqlite3ext.h` 要 `#include "sqlite3.h"`;
而这两个头在多数机器上只随 `libsqlite3-dev` 这类开发包安装,普通用户机器上没有。
把它们随附进仓库,就把「装 libsqlite3-dev」这一步从用户的必备条件里去掉了。

### 复用的既有结论(先查后写)

搜索面:`grep -rniIl "fts5" notes/ reports/ chapters/`(命中 30 个文件),
逐个看过与 `native/fts5_cjk` 有关的那几处。**已有产出、本片不重做**:

| 既有产出 | 它已经说了什么 | 本片关系 |
|---|---|---|
| `notes/r5-10-fts5-session-search.md` §5(第 574-626 行) | 分词器本体的结构级笔记:委托构造 / 回调拦截 / `cjk_emit` 三段切分 / 双入口注册;并已摘录 `build.sh` 的 `-Ivendor` 分支 | **本片的起点**。R5 只说到「无系统头文件时用 `vendor/` 内公版 amalgamation 头,零依赖」,**没有版本号、没有第二个消费者、没有分层处置** |
| `notes/r5-02-hermes-state-sessiondb.md`(第 284、703 行) | `messages_fts_cjk` 在 v23 external-content 布局下的建表、独立标记对、无 tokenizer 时掉触发器 + 置 stale 的降级 | 本片只用它来交代「.so 装好之后谁在用」,不重述 |
| `notes/r5-90-doc-conflict-rulings.md`(第 49-50 行) | 三张 FTS 表的权威三元组 | 引用 |
| `notes/r8a-raw-defaults-b.md`(第 896-897、2102 行) | `sessions.cjk_fts` / `HERMES_CJK_FTS` 配置桥 | 引用 |
| `notes/r8d-02-coverage-audit.md`(第 91 行) | 覆盖审计里 `hermes_state_search + native/fts5_cjk` 记「✅ R5 吸纳后读了」 | 说明:那条勾**不含** `vendor/` 两文件,台账 `status` 至今是 `R1-inventoried` |

台账现状(两行都还没开工过):

```text
native/fts5_cjk/README.md      text  24     L2  R5   R5-deep-read
native/fts5_cjk/build.sh       text  19     L2  R5   R5-deep-read
native/fts5_cjk/fts5_cjk.c     text  252    L2  R5   R5-deep-read
native/fts5_cjk/vendor/sqlite3.h    text  13775  L2  R10  R1-inventoried
native/fts5_cjk/vendor/sqlite3ext.h text  723    L2  R10  R1-inventoried
```

---

## §2 文件清单(逐个全路径)

`native/` 全目录只有 5 个文件,本片是其中 2 个:

| 全路径 | 行数 | 角色一句话 |
|---|---|---|
| `native/fts5_cjk/vendor/sqlite3.h` | 13,775 | SQLite 3.50.4 官方公开 C API 头(amalgamation 形态,末尾追加了 `fts5.h`)。`fts5_cjk.c` 需要的 `fts5_api` / `fts5_tokenizer` / `Fts5Tokenizer` 全在这个追加段里 |
| `native/fts5_cjk/vendor/sqlite3ext.h` | 723 | SQLite 3.50.4 官方**扩展**头:定义 `sqlite3_api_routines` 函数指针表 + `SQLITE_EXTENSION_INIT1/2` 宏 + 把 `sqlite3_xxx()` 重定向到 `sqlite3_api->xxx` 的一大片 `#define`。`fts5_cjk.c` 唯一直接 include 的就是它 |

不在本片、但为讲清楚必须点名的邻居(**已由 R5 覆盖,本片不重读**):
`native/fts5_cjk/fts5_cjk.c`、`native/fts5_cjk/build.sh`、`native/fts5_cjk/README.md`。

---

## §3 接缝穷举

这一片没有 JSON-RPC 方法表 / HTTP 端点表可穷举。它的对外接缝有三个,**都逐项列全**:

### 3.1 接缝 A:`fts5_cjk.c` 从这两个头里消费的上游符号 —— 20 项,全列

机械枚举(把 hermes 自己的入口名与字符串字面量剔掉后逐项分类):

```verify
cd /home/user/hermes-agent && grep -oE \
  '\b(sqlite3(_[a-z0-9_]+)?|SQLITE_[A-Z0-9_]+|fts5_[a-z0-9_]+|Fts5[A-Za-z0-9_]*)\b' \
  native/fts5_cjk/fts5_cjk.c | sort | uniq -c | sort -k2
```

上面输出 22 个唯一标记,其中 2 个不是上游符号:`fts5_api_ptr`(传给
`sqlite3_bind_pointer` 的字符串字面量)、`fts5_cjk`(出现在 hermes 自己的入口名里);
另有 `sqlite3_ftscjk_init` / `sqlite3_fts5_cjk_init` 是**本扩展定义的**入口,不是消费的。
剩下 20 项即完整接缝:

| 类别 | 逐项 | 条数 |
|---|---|---|
| 类型 | `sqlite3`、`sqlite3_stmt`、`sqlite3_api_routines`、`fts5_api`、`fts5_tokenizer`、`Fts5Tokenizer` | 6 |
| 函数 | `sqlite3_bind_pointer`、`sqlite3_finalize`、`sqlite3_free`、`sqlite3_malloc`、`sqlite3_mprintf`、`sqlite3_prepare_v2`、`sqlite3_step` | 7 |
| 宏 / 常量 | `SQLITE_EXTENSION_INIT1`、`SQLITE_EXTENSION_INIT2`、`SQLITE_OK`、`SQLITE_ERROR`、`SQLITE_NOMEM` | 5 |
| `fts5_api` 结构成员(经 `->` 访问,不出现在上面的标识符表里) | `xFindTokenizer`、`xCreateTokenizer` | 2 |
| **合计** | | **20** |

**这 20 项全部是 v1 接口**:`sqlite3_bind_pointer` 是 SQLite 3.20.0 引入的,是其中最年轻的一个;
`fts5_api` 只用了前两个函数成员。代码里**没有** `iVersion` 检查:

```verify
grep -n 'iVersion' /home/user/hermes-agent/native/fts5_cjk/fts5_cjk.c; echo "exit=$? (1 = 零命中)"
```

这一条决定了 §5.3 的跨版本安全性。

### 3.2 接缝 B:整仓对 `fts5_cjk` 的引用 —— 25 处 / 4 文件,全列

```verify
cd /home/user/hermes-agent && grep -rn --binary-files=without-match -I \
  -e fts5_cjk -e FTS5_CJK . --exclude-dir=.git --exclude-dir=native | wc -l
```

读数 **25**;文件面 4 个(同命令去 `-n` 加 `-l` 得到):

| 文件 | 处数 | 干什么 |
|---|---|---|
| `hermes_state.py` | 12 | 路径解析 + 加载 + 4 个加载点 + schema 注释 |
| `tests/test_fts_cjk_bigram.py` | 8 | 现场编译 `.so` 并注入 `HERMES_FTS5_CJK_SO` |
| `hermes_cli/config_defaults.py` | 2 | `sessions.cjk_fts` 的默认值注释里指路 `native/fts5_cjk/build.sh` |
| `.gitignore` | 1 | 忽略构建产物 |

`.gitignore` 那一处(`.gitignore` 无扩展名,校验器的锚点正则认不了,故用 `text` 声明):

```text
# native/fts5_cjk/*.so   —— .gitignore 第 195 行
native/fts5_cjk/*.so
```

### 3.3 接缝 C:`sqlite3_api_routines` 与 `fts5_api` 两张分派表的**版本差** —— 全列

这是本片最实质的接缝:扩展编译时看到的表布局(3.50.4)与运行时宿主递给它的表布局
(取决于宿主 libsqlite3)可能不同。差异可以**逐项穷举**,因为本机恰好装着一份真的
上游 3.45.1 头(Debian `libsqlite3-dev`,`/usr/include/sqlite3ext.h`)可作对照:

```verify
diff -u /usr/include/sqlite3ext.h \
    /home/user/hermes-agent/native/fts5_cjk/vendor/sqlite3ext.h
```

差异**恰好 4 行,2 处,全是追加**(3.45.1 → 3.50.4):

`native/fts5_cjk/vendor/sqlite3ext.h:366-370`

```c
  /* Version 3.44.0 and later */
  void *(*get_clientdata)(sqlite3*,const char*);
  int (*set_clientdata)(sqlite3*, const char*, void*, void(*)(void*));
  /* Version 3.50.0 and later */
  int (*setlk_timeout)(sqlite3*,int,int);
```

`native/fts5_cjk/vendor/sqlite3ext.h:701-705`

```c
/* Version 3.44.0 and later */
#define sqlite3_get_clientdata         sqlite3_api->get_clientdata
#define sqlite3_set_clientdata         sqlite3_api->set_clientdata
/* Version 3.50.0 and later */
#define sqlite3_setlk_timeout          sqlite3_api->setlk_timeout
```

`fts5_api` 那一侧同型 —— 3.50.4 在末尾追加了两个 v2 成员并把 `iVersion` 注释从 2 改成 3:

```verify
cd /home/user/hermes-agent && diff \
  <(sed -n '13336,13390p' /usr/include/sqlite3.h) \
  <(sed -n '13714,13768p' native/fts5_cjk/vendor/sqlite3.h)
```

`native/fts5_cjk/vendor/sqlite3.h:13744-13761`

```c
  /* APIs below this point are only available if iVersion>=3 */

  /* Create a new tokenizer */
  int (*xCreateTokenizer_v2)(
    fts5_api *pApi,
    const char *zName,
    void *pUserData,
    fts5_tokenizer_v2 *pTokenizer,
    void (*xDestroy)(void*)
  );

  /* Find an existing tokenizer */
  int (*xFindTokenizer_v2)(
    fts5_api *pApi,
    const char *zName,
    void **ppUserData,
    fts5_tokenizer_v2 **ppTokenizer
  );
```

**结论(可穷举、不靠推断)**:3.45.1 与 3.50.4 之间,这两张表的差异**只有追加**,
`fts5_cjk.c` 用到的 20 项全部落在两版共有的前缀里,偏移完全一致。

---

## §4 端到端链:从「用户敲一条命令」到「随附头文件被真正用上」

这一片在链条的**编译期**那一段。逐跳带锚点;两端接给谁写清。

**跳 0(链条上游,不在本片)**:用户在 `~/.hermes/config.yaml` 留 `sessions.cjk_fts`
(默认 `True`),会话检索走 `messages_fts_cjk` —— 由 R5 覆盖,见
`notes/r5-10-fts5-session-search.md` §1.4。

**跳 1:用户手动跑 `./build.sh`(或 pytest 跑 fixture),这是唯一两条编译入口。**

`native/fts5_cjk/build.sh:10-15`

```bash
CFLAGS_EXTRA=""
if ! echo '#include <sqlite3ext.h>' | gcc -E -xc - >/dev/null 2>&1; then
  CFLAGS_EXTRA="-Ivendor"
fi

gcc -shared -fPIC -O2 -Wall -Wextra $CFLAGS_EXTRA fts5_cjk.c -o libfts5_cjk.so
```

即:**先探测系统有没有 `sqlite3ext.h`,没有才把 `vendor/` 加进头文件搜索路径**。
本片两个文件在这条路上是**兜底**。

**跳 1′:测试 fixture 的编译入口 —— 无条件用 `vendor/`。**

`tests/test_fts_cjk_bigram.py:16-18`

```python
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "native" / "fts5_cjk" / "fts5_cjk.c"
VENDOR = REPO / "native" / "fts5_cjk" / "vendor"
```

`tests/test_fts_cjk_bigram.py:27-31`

```python
        subprocess.run(
            ["gcc", "-shared", "-fPIC", "-O2", f"-I{VENDOR}", str(SRC),
             "-o", str(out)],
            check=True, capture_output=True, text=True,
        )
```

`-I{VENDOR}` **没有任何条件**。`gcc` 先搜 `-I` 目录再搜系统目录,所以哪怕机器上装了
`libsqlite3-dev`,测试编出来的 `.so` 也是照着**本片这两个 3.50.4 头**编的。
CI 会跑到它:`.github/workflows/tests.yml` 第 132 行调 `scripts/run_tests.sh --files ...`,
切片来自 `scripts/run_tests_parallel.py`,后者按下面这一行枚举 `tests/`,
`tests/test_fts_cjk_bigram.py` 在内。
(注:`.github/...` 这类以点开头的路径写成 `路径:行号` 时,校验器的路径正则
`[A-Za-z0-9_][A-Za-z0-9_./-]*` 会把前导点吃掉、得到解析不了的 `github/workflows/...`,
所以本底稿对 `.github/` 下的位置一律写成"第 N 行"的散文形式,不写成锚点。)

`scripts/run_tests_parallel.py:162`

```python
        for path in root.rglob("test_*.py"):
```

**跳 2:`#include` 链把两个头一起拖进来。**

`native/fts5_cjk/fts5_cjk.c:26-27`

```c
#include <sqlite3ext.h>
SQLITE_EXTENSION_INIT1
```

`native/fts5_cjk/vendor/sqlite3ext.h:19-20`

```c
#define SQLITE3EXT_H
#include "sqlite3.h"
```

注意这里是**双引号** include:C 的双引号形式先在「包含它的那个文件所在目录」里找。
所以一旦 `vendor/sqlite3ext.h` 被选中,`vendor/sqlite3.h` 就**必然**跟着被选中 ——
两个文件必须成对随附,不能只留一个。这也解释了为什么一个只 include 了
`sqlite3ext.h` 的 252 行 C 文件,会拖着 13,775 行的 `sqlite3.h` 进仓库。

**跳 3:`sqlite3.h` 末尾的 fts5 追加段提供 `fts5_api`,分词器才注册得上。**

`native/fts5_cjk/vendor/sqlite3.h:13018-13019`

```c
/******** End of sqlite3session.h *********/
/******** Begin file fts5.h *********/
```

`native/fts5_cjk/vendor/sqlite3.h:13714-13716`

```c
typedef struct fts5_api fts5_api;
struct fts5_api {
  int iVersion;                   /* Currently always set to 3 */
```

**跳 4(链条下游,不在本片)**:`.so` 落到 `~/.hermes/lib/`,由 Python 侧加载。

`hermes_state.py:1631-1636`

```python
def fts5_cjk_so_path() -> Path:
    """Location of the cjk_unicode61 loadable extension."""
    env = os.getenv("HERMES_FTS5_CJK_SO")
    if env:
        return Path(env).expanduser()
    return get_hermes_home() / "lib" / "libfts5_cjk.so"
```

`hermes_state.py:1646-1653`

```python
def load_fts5_cjk_extension(conn: sqlite3.Connection) -> bool:
    """Best-effort load of the cjk_unicode61 tokenizer into ``conn``.

    Returns False (never raises) when the .so is absent, the feature is
    disabled via ``sessions.cjk_fts``, or this Python build has extension
    loading compiled out — every caller treats False as "behave exactly as
    before the cjk index existed".
    """
```

加载点 4 个,已逐个定位(函数名由行号上溯 `def`/`class` 得到):

| 加载点 | 所在函数 |
|---|---|
| `hermes_state.py:1263`:`load_fts5_cjk_extension(conn)` | `_db_opens_cleanly`(健康探测,第 1244 行) |
| `hermes_state.py:1427`:`load_fts5_cjk_extension(conn)` | `repair_state_db_schema`(自愈,第 1370 行) |
| `hermes_state.py:2161`:`self._fts_cjk_loaded = load_fts5_cjk_extension(self._conn)` | `SessionDB.__init__` 的写连接(第 2005 行) |
| `hermes_state.py:2288`:`load_fts5_cjk_extension(conn)` | `SessionDB._get_read_conn`(读连接,第 2253 行) |

可加载扩展是**挂在连接上、不是挂在数据库文件上**,所以读连接也要各自 load ——
这一点 R5 已讲过,本片只补齐「四个点都在」。

**本片这一段走通的证据(受控复现,不写基线)**:用基线的 `vendor/` 头把 `fts5_cjk.c`
编成 `.so` 放进临时目录,再装进本容器 Python 的 SQLite 里跑双字查询。

```verify
V=/home/user/hermes-agent/native/fts5_cjk/vendor
gcc -shared -fPIC -O2 -Wall -Wextra -I"$V" \
    /home/user/hermes-agent/native/fts5_cjk/fts5_cjk.c -o /tmp/libfts5_cjk.so
/home/user/hermes-venv/bin/python - <<'PY'
import sqlite3
print("runtime sqlite:", sqlite3.sqlite_version)
c = sqlite3.connect(":memory:"); c.enable_load_extension(True)
c.load_extension("/tmp/libfts5_cjk.so")
c.execute("CREATE VIRTUAL TABLE t USING fts5(body, tokenize='cjk_unicode61')")
c.execute("INSERT INTO t(body) VALUES ('웅기가말했다')")
print(c.execute("SELECT body FROM t WHERE t MATCH ?", ('"말했"',)).fetchall())
PY
```

实测输出(`console` 声明,非源码):

```console
runtime sqlite: 3.45.1
[('웅기가말했다',)]
```

`gcc` 零告警(开了 `-Wall -Wextra`),`.so` 15,936 字节;2 字查询命中 6 字连串内部
—— 即「3.50.4 头编出来的扩展,装进 3.45.1 运行时,双字语义成立」。

---

## §5 逐机制结构笔记(四问)

### 5.1 (a) 是不是逐字上游?版本多少?与本容器的 SQLite 什么关系?

**是逐字上游,版本 3.50.4(2025-07-30)。** 五条独立证据(①–⑤):

**① 版本三元组就在头里。**

`native/fts5_cjk/vendor/sqlite3.h:149-151`

```c
#define SQLITE_VERSION        "3.50.4"
#define SQLITE_VERSION_NUMBER 3050004
#define SQLITE_SOURCE_ID      "2025-07-30 19:33:53 4d8adfb30e03f9cf27f800a2c1ba3c48fb4ca1b08b0f5ed59a4d5ecbf45e20a3"
```

```verify
grep -nE '^#define SQLITE_(VERSION|VERSION_NUMBER|SOURCE_ID) ' \
    /home/user/hermes-agent/native/fts5_cjk/vendor/sqlite3.h
```

`SQLITE_SOURCE_ID` 的后半是上游对源码树算的 SHA3-256,是自识别指纹。
`sqlite3ext.h` 自己不带版本宏(它 include `sqlite3.h` 取),其版本由 §3.3 的
`/* Version 3.50.0 and later */` 段落坐实。

**② 是 amalgamation 形态,不是源码树里的 `src/sqlite.h.in`。**
上游只在合并发行版里把 `fts5.h` 追加到 `sqlite3.h` 末尾并留下分节横幅,
`native/fts5_cjk/vendor/sqlite3.h:13018-13019` 那两行横幅就是这个形态的指纹
(§4 跳 3 已摘)。文件最后一行是 `#endif /* SQLITE3_H */`(第 13775 行),
也就是说**整个文件到末尾都还在上游的头文件保护宏里,没有任何本地追加**。

**③ 与一份真上游头逐行对照,差异只有版本演进。**
本容器装了 Debian 的 `libsqlite3-dev`(`dpkg -S /usr/include/sqlite3.h` →
`libsqlite3-dev:amd64`),其 `sqlite3.h` 是上游 3.45.1。对照结果:

| 对照 | 读数 | 差异性质 |
|---|---|---|
| `sqlite3ext.h`(719 → 723 行) | 2 hunk / +4 行 / −0 行 | 全是 3.50.0 的 `setlk_timeout` 追加(§3.3 已逐项列全) |
| `sqlite3.h`(13,377 → 13,775 行) | 120 hunk / +563 / −173 | 全是 3.46–3.50 的上游新增与文档改写 |

`sqlite3.h` 那 120 个 hunk 里新引入的符号(机械抽取)全部是真实的上游 3.46–3.50 新增,
逐个可对上游 changelog:`SQLITE_CONFIG_ROWID_IN_VIEW`(3.46)、`SQLITE_INDEX_SCAN_HEX`(3.48)、
`SQLITE_DBCONFIG_ENABLE_COMMENTS` / `SQLITE_DBCONFIG_ENABLE_ATTACH_CREATE` /
`SQLITE_DBCONFIG_ENABLE_ATTACH_WRITE` / `SQLITE_FCNTL_BLOCK_ON_CONNECT`(3.49)、
`sqlite3_setlk_timeout` / `SQLITE_SETLK_BLOCK_ON_CONNECT` / `SQLITE_ENABLE_SETLK_TIMEOUT`(3.50)、
`sqlite3_rsync`(3.50 的新工具)。fts5 追加段内的 148 行差异按模式归类是 v2
(locale 感知)分词器接口:`fts5_tokenizer_v2` 9 处、`xCreateTokenizer_v2` 2 处、
`xFindTokenizer_v2` 2 处、`pLocale` 9 处、`nLocale` 7 处、`xColumnLocale` 2 处;
把这些模式排除后剩下的行,抽查全部是 `**` 开头的注释散文。

```verify
diff <(sed -n '12751,13377p' /usr/include/sqlite3.h) \
     <(sed -n '13019,13775p' /home/user/hermes-agent/native/fts5_cjk/vendor/sqlite3.h) \
  | grep -c '^[<>]'
```

**④ 零本地改动痕迹。**(负结论,搜索面写全)
搜索面 = 这**两个文件的全部 14,498 行**,大小写不敏感,模式为
`hermes|cjk|unicode61|\bnous\b|bigram` —— 即「若有人为 hermes 的需要动过这两个头,
最可能留下的五类痕迹」。`\bnous\b` 加词边界是**故意的**:不加词边界时
`nous` 会命中 `synchro`**`nous`**(实测 3 处,`sqlite3.h:712`、`713`、`934`),
那种「命中」与本结论正好相反,属于本项目明令要防的形状。

```verify
grep -c -i -E 'hermes|cjk|unicode61|\bnous\b|bigram' \
    /home/user/hermes-agent/native/fts5_cjk/vendor/sqlite3.h \
    /home/user/hermes-agent/native/fts5_cjk/vendor/sqlite3ext.h
```

读数为两个 `0`。**未排除的可能**:上游有可能被人做了「不留这五类词」的改动
(例如悄悄改一个常量值)。要彻底排除只能拿官方 3.50.4 amalgamation 逐字 diff,
而这条路本轮被网络策略挡住,见 §7 的拦截记录。

**⑤ git 侧旁证**:这两个文件自加入起从未被改过 —— 单一 commit,与分词器同批引入。

```verify
git -C /home/user/hermes-agent log --oneline -- native/fts5_cjk/vendor/ | cat
```

```console
f13f84511 feat(state): messages_fts_cjk — CJK-bigram index on the v23 external-content layout
```

#### 与本容器 SQLite 的关系 —— 三个读数,分别标注,**不是「一致」**

| 读数 | 值 | 来源 |
|---|---|---|
| 随附头文件声明的版本 | **3.50.4**(2025-07-30) | `native/fts5_cjk/vendor/sqlite3.h:149` 的 `#define SQLITE_VERSION        "3.50.4"` |
| 本容器学习用 venv 的运行时 SQLite | **3.45.1** | `/home/user/hermes-venv/bin/python -c "import sqlite3;print(sqlite3.sqlite_version)"` |
| 本容器系统开发头(对照用) | **3.45.1**(`SOURCE_ID` 为 Debian 的 `...ccalt1` 变体) | `/usr/include/sqlite3.h:149`(非基线文件) |

**三者不一致,差 5 个小版本。** 但这不是随手拿了个新版:3.50.4 恰好是 **Hermes 自己托管的
Python 运行时所链接的 SQLite 版本**,基线代码里两处独立地把这个数写死在注释里:

`hermes_cli/managed_uv.py:438-441`

```python
    Requesting the exact patch can never repair some installs: for a given
    patch, python-build-standalone may have no artifact with fixed SQLite at
    all (e.g. every published 3.11.14 build links SQLite 3.50.4; the fix
    only exists from 3.11.15).  A newer patch on the same minor is what
```

`hermes_state.py:681-684`

```python
    WAL result came from SQLite 3.53.1, which carries BOTH the WAL-reset fix
    AND 3.51.0's defenses against close()-broken POSIX locks, so it says
    nothing about 3.50.4.  Re-measured on the actually-bundled 3.50.4 with
    the lock fix in place, WAL and DELETE are both clean (0/3 each) — i.e.
```

即:**随附头文件的版本 = Hermes 实际跑的那个 SQLite 的版本**(3.50.4),
而不是本学习容器里 Debian Python 的 3.45.1。本容器的 3.45.1 只是学习环境的性质,
与基线无关(与 CLAUDE.md 里「venv 是便利设施、不是引用基准」同一条口径)。
**「版本对齐是有意的」这一点属推定**,见 §7 —— 仓库里没有任何文字这么说。

### 5.2 (b) `native/fts5_cjk/` 是干什么的?谁编译、谁加载?

**干什么(复用 R5,不重述细节)**:SQLite 自带的 `unicode61` 分词器把一整串 CJK 当**一个**
token(`웅기가말했다` = 一个 6 字 token),于是 2 字查询永远匹配不进去;自带的 `trigram`
分词器修得了子串检索但每个查询词要 ≥3 字符,2 字韩语词(`일본`、`구글`……)因此落到
LIKE 全表扫描,在 6.8GB 的 messages 表上实测每次查询 3–6 秒,是会话检索延迟的第一驱动。
`cjk_unicode61` 的做法是**包装** `unicode61`:把它吐出的每个 token 再过一遍,内部的
CJK 连段重发射为重叠双字,非 CJK 段原样透传;FTS5 会把一个查询词产生的连续 token 当短语,
于是 `캘린더` → `[캘린][린더]` 得到索引速度的精确子串语义,下探到 2 字。
—— 出处 `notes/r5-10-fts5-session-search.md` §5.1(该节已逐字摘录
`native/fts5_cjk/fts5_cjk.c:1-18` 的自述)。

**谁编译 —— 两条入口,全列**(见 §4 跳 1 / 跳 1′):

1. `native/fts5_cjk/build.sh` —— **用户手动跑**,系统头缺失时才用 `vendor/`;
2. `tests/test_fts_cjk_bigram.py` 的 session 级 fixture —— **无条件**用 `vendor/`,CI 每轮都跑。

**负结论:全仓没有任何自动构建 / 打包 / 安装这个扩展的路径。** 搜索面写全:

- 搜索面 1:`grep -rn -e fts5_cjk -e FTS5_CJK` 全仓(排除 `.git` 与 `native/`)→ 25 处 / 4 文件,
  已在 §3.2 逐个列出;这 4 个文件里**没有**任何构建脚本。
- 搜索面 2:对 `setup-hermes.sh`、`scripts/`(113 文件,含 `install.sh` / `install.ps1` /
  `install.cmd`)、`docker/`(18)、`nix/`(16)、`.github/`(42)、`pyproject.toml`、`setup.py`
  合计 **193 个文件**搜 `fts5|libfts5|native/`,**零命中**:

  ```verify
  cd /home/user/hermes-agent && grep -rn --binary-files=without-match -I \
    -e 'fts5' -e 'libfts5' -e 'native/' \
    setup-hermes.sh scripts/ docker/ nix/ .github/ pyproject.toml setup.py; \
    echo "exit=$? (1 = 零命中)"
  ```

- 搜索面 3:构建系统面。全仓 `find` 只有 `./setup.py`(其内容是**禁止**打 wheel/sdist 的守卫)、
  `./hermes_cli/setup.py`、`./hermes_cli/subcommands/setup.py`(CLI 子命令,不是 setuptools)、
  以及 `skills/` 与 `research-paper-writing/templates/` 下两个与本片无关的文件;
  **没有 `CMakeLists.txt` / `meson.build` / 根 `Makefile`**,`pyproject.toml` 里**没有** `ext-modules`。
- **未排除**:我没有搜 git 历史与其它分支;也没有验证仓库外的 shell 安装器(官网下载的那个)
  会不会跑 `build.sh` —— 那不在基线里,看不到。

**谁加载**:`hermes_state.py` 的 4 个点,已在 §4 跳 4 逐个列出;语义是
best-effort(缺 `.so` / 关配置 / Python 编译时没开扩展加载,一律返回 `False` 不抛)。

### 5.3 (c) 分层判断:L2 还是 L4?—— **建议改 L4**

**先查清是哪条规则把它们判成 L2 的。** 不是针对这两个文件的判断,而是一条目录级 catch-all:

`scripts/assign_layers.py:619-623`

```python
    # R5 吸纳:FTS5 CJK 分词器本体(vendored sqlite 头文件仍留 R10)
    ("native/fts5_cjk/fts5_cjk.c", "L2", "R5"),
    ("native/fts5_cjk/build.sh", "L2", "R5"),
    ("native/fts5_cjk/README.md", "L2", "R5"),
    ("native/**", "L2", "R10"),
```

规则是「首条匹配生效」。三条显式行把分词器本体挑给 R5,第 4 行
`("native/**", "L2", "R10")` 兜住目录里余下的一切 —— 也就是本片这两个头文件。
**它们的 L2 是被目录兜底兜出来的,不是有人判过。**

**L4 的定义里字面就写着 vendored。**

`scripts/assign_layers.py:11`

```python
  L4  有理由排除   — generated / vendored / binary / media / lockfiles; justified skip
```

**判断:这两个文件符合 L4 的字面定义,建议改 L4,`round` 改 `-`。** 依据四条:

1. **性质就是 vendored**:§5.1 的五条证据坐实它们是逐字上游 3.50.4,自加入起未被改动,
   零本地痕迹。它们不是 hermes 的设计产出,读它们学到的是 SQLite 的 C API,不是 harness。
2. **L2 的判据在这里没有可执行的内容**。本轮派工书对 L2 的定义是「读接口面而不读实现体,
   把方法表列全」。这两个文件**通篇就是接口面**(纯声明,零实现体)。
   照字面执行 L2 = 把 SQLite 全部 ~300 个公开 API 列成表 —— 那是 SQLite 的文档工作,
   与「独立设计一个 agent harness」这个最终目的没有交点。
3. **真正有价值的那一小片已被 L2 覆盖了**:hermes 代码只碰这两个头里的 20 个符号(§3.1),
   而这 20 个符号的用法在 `native/fts5_cjk/fts5_cjk.c`(已 L2 / R5-deep-read)里全都有。
   把 14,498 行标 L2 而其中只有 20 个符号进入过任何产出,会让 L2 这个层失去意义。
4. **上游作者自己就是这个态度**(旁证,不是本项目的规则):hermes 自带的代码文档技能
   把 vendored 目录列为明确跳过项。

   `website/docs/user-guide/skills/optional/software-development/software-development-code-wiki.md:418`

   > - Skip vendored code (`vendor/`, `third_party/`, generated code, `_pb2.py`, `.min.js`)

   同一态度也出现在 `.github/workflows/osv-scanner.yml` 第 46 行(见 §6 的「一致」项)。

**保留 L2 的反方理由(如实列出,不藏)**:这两个文件确实是仓库**真的会编译进去**的接口,
不像 `package-lock.json` 那样只是被工具读;而 `fts5_api` 结构(`sqlite3.h:13714-13762`)
是分词器能注册上的唯一原因,算得上"载荷"。我认为这个理由不足以撑住 L2,因为
**载荷部分是 20 个符号,不是 14,498 行**;把它作为 L4 并在台账里指向本底稿,
信息不损失、而分层恢复了可解释性。

**给 R11/R12 的具体建议(不由本片执行 —— 台账由主线统一更新)**:

- `data/ledger.tsv` 两行 `layer` 由 `L2` 改 `L4`,`round` 由 `R10` 改 `-`,
  `status` 记成可翻译成「学到什么程度」的形态,建议 `R10-vendored-justified-skip`。
- 五层加总不变(仍 = 2,608,452 行),只是 L2 减 14,498、L4 加 14,498;`R1-inventoried`
  剩余数减 2 个文件 / 14,498 行 —— 这是本片对「全仓无黑洞」指标的实际贡献。
- `scripts/assign_layers.py` 若要让规则自解释,可在第 619 行那组显式行**之前**加一条
  `("native/**/vendor/**", "L4", "-")`,理由写「随附上游源码」。**本片不改脚本**(铁律 2)。

### 5.4 (d) 被什么构建步骤用到?

汇总(逐项带出处,搜索面见 §5.2 的三个搜索面):

| 构建步骤 | 是否用到 `vendor/` | 出处 |
|---|---|---|
| `native/fts5_cjk/build.sh`(用户手动) | **条件用**:仅当 `gcc -E` 找不到系统 `sqlite3ext.h` 时加 `-Ivendor` | `native/fts5_cjk/build.sh:12`:`CFLAGS_EXTRA="-Ivendor"` |
| `tests/test_fts_cjk_bigram.py` fixture(pytest / CI) | **无条件用**:`-I{VENDOR}` 永远在命令里 | `tests/test_fts_cjk_bigram.py:28`:`f"-I{VENDOR}", str(SRC),` |
| Python 打包(`setup.py` / `pyproject.toml`) | **不用**。根 `setup.py` 是禁止打 wheel/sdist 的守卫;`packages.find` 不含 `native` | `pyproject.toml:398`:`[tool.setuptools.packages.find]`(全文见下方摘录) |
| Docker / Nix / CI workflow / 安装器 | **不用**(193 文件零命中,见 §5.2 搜索面 2) | 同上 |
| `CMakeLists.txt` / `Makefile` / `meson.build` | **不存在**(与本片相关的一个都没有) | §5.2 搜索面 3 |

`pyproject.toml:398-399`

```toml
[tool.setuptools.packages.find]
include = ["agent", "agent.*", "tools", "tools.*", "hermes_cli", "hermes_cli.*", "gateway", "gateway.*", "tui_gateway", "tui_gateway.*", "cron", "cron.*", "acp_adapter", "plugins", "plugins.*", "providers", "providers.*"]
```

**一句话**:本片两个文件在**用户手动构建**里是兜底、在**测试/CI 构建**里是唯一权威,
在**发行打包**里根本不参与。

---

## §6 发现清单

### ◇1 `vendor/` 不只是「没装 libsqlite3-dev 时的兜底」——测试路径无条件用它,而这一点没有任何文档

`native/fts5_cjk/README.md:11-12`

> Uses the system `sqlite3ext.h` when available, else the vendored copy in
> `vendor/` — no libsqlite3-dev required.

这句话挂在 README 的 "Build & install to `~/.hermes/lib/`: `./build.sh`" 之下,
**对 `build.sh` 而言字面为真** —— 它那句探测就是这么写的:

`native/fts5_cjk/build.sh:11-12`

```bash
if ! echo '#include <sqlite3ext.h>' | gcc -E -xc - >/dev/null 2>&1; then
  CFLAGS_EXTRA="-Ivendor"
```

所以**这不是 ▲** —— 按本项目「判定一条文档断言要连整段、并确认它归哪个标题管」的规则,
这条断言的管辖范围是 `native/fts5_cjk/build.sh`,不是整个仓库。

但**第二个消费者存在且行为相反**:

`tests/test_fts_cjk_bigram.py:28`

```python
            ["gcc", "-shared", "-fPIC", "-O2", f"-I{VENDOR}", str(SRC),
```

`-I{VENDOR}` 无条件写进 gcc 命令行,而 `-I` 目录先于系统目录被搜索。
后果:**CI 每一轮编出来的 `.so` 都是照 3.50.4 头编的,与 runner 上装没装
`libsqlite3-dev` 无关**。而第三处提到构建的地方也只提 `build.sh`:

`hermes_cli/config_defaults.py:2708-2711`

```python
        # CJK-bigram search index (messages_fts_cjk, cjk_unicode61 loadable
        # tokenizer). When the extension is built (native/fts5_cjk/build.sh →
        # ~/.hermes/lib/libfts5_cjk.so), 1-2 char CJK terms (일본, 项目, ...)
        # get index-speed exact matching instead of LIKE full-table scans.
```

`README.md`、`build.sh` 的注释、上面这段配置注释,三处都只提 `build.sh`,
没有一处提到测试也在编、更没提它不走探测。
→ **◇(代码有、文档无)**。对读者的实际影响:照 README 理解,会以为装了
`libsqlite3-dev` 的机器根本用不到 `vendor/`,于是把这两个文件当纯冗余 —— 删掉它们
CI 就红。

### ◇2 随附版本 3.50.4 的来源与刷新策略,在仓库里没有任何记录

`SQLITE_VERSION "3.50.4"` 只存在于头文件自己内部。负结论,搜索面写全:全仓
(排除 `.git`)搜 `3\.50\.4` / `3050004` / `4d8adfb30e03f9cf`,**排除 `native/fts5_cjk/vendor/` 自身**:

```verify
cd /home/user/hermes-agent && grep -rn --binary-files=without-match -I \
  -e '3\.50\.4' -e '3050004' -e '4d8adfb30e03f9cf' . --exclude-dir=.git \
  | grep -v '^\./native/fts5_cjk/vendor/'
```

命中 11 处,分布在 5 个文件:`hermes_state.py`(1)、`hermes_cli/managed_uv.py`(1)、
`tests/hermes_cli/test_managed_uv.py`(6)、`tests/test_sqlite_wal_reset_gate.py`(2)、
`tests/conftest.py`(1) —— **全部在讲「托管运行时链接的 SQLite 是 3.50.4」这件事,
没有一处提到随附头文件**。也就是说:两处 3.50.4 数值相同、语义相关,却**互不引用**。
没有 `vendor/README`、没有版本戳文件、没有「头文件版本须跟随托管运行时」的检查。
后果:当托管运行时按下面这条路径升到 3.11.15+(SQLite 3.53.1)时,
`vendor/` 会静默停在 3.50.4,没有任何机制会指出这件事。

`hermes_cli/managed_uv.py:441`

```python
    only exists from 3.11.15).  A newer patch on the same minor is what
```

→ **◇**。**这不是 ■**:头文件是纯声明,停在旧版只会「编出来的扩展少用几个新 API」,
不会产生错误行为(理由见 §3.3 的「只有追加」结论)。

### ◇3 跨版本加载的安全性依赖一条没写下来的不变量

编译期看到的分派表是 3.50.4 的(2 张表都比 3.45.1 长),运行期宿主递过来的表可能是旧版的短表。
安全的唯一原因是:`fts5_cjk.c` 只碰两版共有的前缀(§3.1 的 20 项全是 v1),
所以所有偏移一致。但代码里**没有 `iVersion` 检查**(§3.1 的零命中 verify)、
`fts5_cjk.c` 的文件头注释与 `build.sh` 的注释里**也没有一句**交代「不许用 v2 成员」。
→ **◇**。这是一条会被后来者踩的隐式约束:哪天有人想用 `xCreateTokenizer_v2`
拿 locale 感知能力,在 3.50.4 头下编得过、在 3.45.1 宿主上就是读越界。
(本片实测「3.50.4 头 + 3.45.1 宿主」工作正常,见 §4 末的 `console` 读数
—— 那**恰好**验证的是这条不变量当前成立,不是验证它被保护着。)

### 一致(核过但不成记号,列出以免下一轮重查)

| 断言 | 判定 |
|---|---|
| `native/fts5_cjk/build.sh:5`:`vendor/ (public-domain SQLite amalgamation headers) so the build works` | **成立且可验**:公版声明见 `vendor/sqlite3.h` 第 1-10 行的 "The author disclaims copyright…";amalgamation 形态见 `vendor/sqlite3.h` 第 13019 行的 `/******** Begin file fts5.h *********/` 横幅 |
| `native/fts5_cjk/README.md:12`:`no libsqlite3-dev required.` | 成立(对 `build.sh` 而言),见 ◇1 的范围判定 |
| `.github/workflows/osv-scanner.yml` 第 45-46 行明说只扫 5 个 lockfile、"skip vendored / test / worktree dirs" | 成立。**所以「随附头文件不在供应链扫描面内」是声明过的取舍,不是漏洞**,不记 ◇ |
| `notes/r5-10-fts5-session-search.md` §5.2 关于 `-Ivendor` 兜底的叙述 | 与 `native/fts5_cjk/build.sh:12`:`CFLAGS_EXTRA="-Ivendor"` 一致(本片只是补上了它没说的版本与第二个消费者) |

---

## §7 未取证与推定

1. **没有拿官方 3.50.4 amalgamation 做逐字 diff。** 唯一确定性的「逐字上游」证明是把上游
   压缩包下来对比,本轮被网络策略挡住:
   ```console
   curl -sSL https://sqlite.org/2025/sqlite-amalgamation-3500400.zip
   curl: (56) CONNECT tunnel failed, response 403
   ```
   代理状态里对应记录为 `{"kind":"connect_rejected","host":"sqlite.org:443"}`。
   **需放行项:`sqlite.org:443`**(若要在后续轮里把 §5.1 的④从「零改动痕迹」升级为
   「逐字全等 + SHA256 对上上游」)。目前 §5.1 给的是 5 条**旁证**,不是全等证明。
2. **「头文件版本刻意对齐托管运行时的 3.50.4」是推定。** 事实层面两个 3.50.4 一致
   (`vendor/sqlite3.h:149` 与 `hermes_cli/managed_uv.py:440`),但仓库里没有任何文字
   把两者联系起来(◇2 的搜索面已证明),所以「有意对齐」只是最省的解释,不是取证结论。
   也可能只是引入者当时随手拿了最新稳定版而恰好同版。
3. **`build.sh` 的能力探测测的是代理信号,不是所需能力 —— 我没有拿到真实会触发的环境。**
   探测编译的是 `#include <sqlite3ext.h>`,而编译真正需要的是 `sqlite3.h` 里的
   `fts5_api` / `fts5_tokenizer`。理论上存在「系统有 `sqlite3ext.h` 但 `sqlite3.h` 无 fts5 段」
   的机器,此时探测通过、`-Ivendor` 不加、编译在 `fts5_tokenizer` 处失败。我做过一次
   受控复现(把系统头在 fts5 段之前截断后编译,确实报 `unknown type name 'fts5_tokenizer'`),
   但要如实说两点:**(i)** 那是我造出来的环境,不是自然出现的;**(ii)** 我的截断做得很粗,
   同一次编译还附带报了一个 `#endif without #if`,所以那次复现只说明了方向,
   **不能当干净证据**。而现实触发条件(sqlite3.h 老于 3.9,即 fts5.h 出现之前)
   在 2026 年基本绝迹。**故不记 ■**,只作为设计教训记在这里:
   能力探测应当探测所需能力本身,而不是它的代理物。
4. **没有读 13,775 行 `sqlite3.h` 的正文。** 这是本片的**设计**(见 §5.3 判断 2),
   不是欠账。实读的是:版本宏段、amalgamation 分节横幅、文件尾、`fts5_api` 结构全文
   (`13714-13762`)、以及与 3.45.1 的全量 diff(120 hunk 全过了一遍分类,
   未逐 hunk 阅读正文)。
5. **`sqlite3ext.h` 读全了**(723 行里,`sqlite3_api_routines` 结构与 `#define`
   重定向区是通过与 3.45.1 的全量 diff 逐行核过的:2 hunk / 4 行差异,已在 §3.3 列全)。
6. **没有跑 `tests/test_fts_cjk_bigram.py`** —— 这是一个如实的缺项,不是做不到:
   它需要的 `gcc` 与扩展加载在本容器都可用,跑它也不需要装任何包。没跑的原因是
   §4 末的受控复现已经把同一条路(vendor 头 → gcc → `load_extension` → 双字命中)
   走通了,本片的四问都不依赖该用例的通过与否。**所以本底稿不报任何测试通过数**
   (按项目规则,报测试数必须同时记环境;本片没有测试数可报)。

---

## §8 L2 判据自评

| # | 判据 | 自评 |
|---|---|---|
| 1 | **点名到位**:片内每个文件至少一次全路径 + 一句话角色 | ✅ 2/2。`native/fts5_cjk/vendor/sqlite3.h`、`native/fts5_cjk/vendor/sqlite3ext.h` 在 §2 表里各一行角色说明,正文另各出现多次 |
| 2 | **接缝穷举**:逐项列全 + 机械枚举命令 + 条数 | ✅ 三个接缝全列:A 上游符号 **20 项**(枚举命令在 §3.1);B 整仓引用 **25 处 / 4 文件**(命令在 §3.2);C 两张分派表版本差 **`sqlite3ext.h` 2 hunk / 4 行**、**`fts5_api` +2 成员**(命令在 §3.3)。无抽样 |
| 3 | **一条端到端链走通,逐跳带锚点** | ✅ §4 五跳,全部带锚点:`native/fts5_cjk/build.sh` 与 `tests/test_fts_cjk_bigram.py` 的两条编译入口 → `native/fts5_cjk/fts5_cjk.c` 的 include → `vendor/sqlite3ext.h` 的双引号 include → `vendor/sqlite3.h` 的 fts5 追加段与 `fts5_api` → `hermes_state.py` 的路径解析、加载函数与 4 个加载点。两端接谁写明(上游 = `sessions.cjk_fts` 配置,R5 覆盖;下游 = `SessionDB` 连接,R5 覆盖)。链条在本片内的那一段(编译期)另有一次可复现的实跑 |
| 4 | **两处以上逐字取证** | ✅ 逐字围栏块 **23 个**(基线 21 + study 侧 2),均用 `sed -n` 取出后粘贴、未手抄:`native/fts5_cjk/vendor/sqlite3.h` 4、`native/fts5_cjk/vendor/sqlite3ext.h` 3、`native/fts5_cjk/build.sh` 2、`tests/test_fts_cjk_bigram.py` 3、`native/fts5_cjk/fts5_cjk.c` 1、`hermes_state.py` 3、`hermes_cli/managed_uv.py` 2、`hermes_cli/config_defaults.py` 1、`scripts/run_tests_parallel.py` 1、`pyproject.toml` 1;study 侧 `scripts/assign_layers.py` 2。另有 2 个 `>` 引用块,分别摘 `website/docs/user-guide/skills/optional/software-development/software-development-code-wiki.md` 第 418 行与 `native/fts5_cjk/README.md` 第 11-12 行 |
| 5 | **至少一条记号** | ✅ 3 条 ◇(◇1 测试无条件用 vendor 且无文档 / ◇2 版本来源与刷新策略无记录 / ◇3 跨版本不变量未写下)。■▲◎ 各 0 —— 考虑过一条 ■(`build.sh` 探测代理信号)与一条 ▲(README 的 "when available"),两条都**主动否决**并写明理由(§7-3、§6-◇1) |

**引用校验读数**:`citations=20 OK=18 UNCHECKED=2`,可校验比例 **90.0%**(≥70% 下限);
`table_anchors=14 OK=14`,MISMATCH / BLOCK-DRIFT / TABLE-DRIFT 各 0,退出码 0。
2 处 UNCHECKED 是散文式区域指路(§5.2 指向 R5 底稿已逐字摘录过的
`native/fts5_cjk/fts5_cjk.c` 文件头自述,以及 §7 里一句同时点两个位置的话)。

**额外说明 —— 本底稿有 7 个围栏块是关卡看不见的,所以自己补了一道校验。**
`vendor/*.h` 的锚点**不会**被 `scripts/verify_citations.py` 机械校验:
它的路径正则只认 `py md yaml yml toml c sh json ts tsx js` 十一种扩展、**没有 `h`**
(见 §9 的 H-R10I-d)。全篇提到 `.h` 具体位置共 13 处,其中 **7 处是「锚点 + 逐字围栏块」**
—— 这 7 块**不进 citations 计数、也不被比对**。这不是理论风险:本底稿定稿前
自查就抓到 1 处真漂移(`sqlite3ext.h` 那一块实际起于第 19 行,锚点写了 18)
和 2 处「声明区间比块少一行」,而当时官方关卡是全绿的。
下面这段脚本按围栏校验器的同一规则(空白不敏感、逐行到块尾、并额外核对声明区间与块行数一致)
把这 7 块重跑一遍,当前输出 `checked=7 problems=0`:

```verify
cd /home/user/hermes-study && python3 - <<'PY'
import re
from pathlib import Path
note = Path('notes/r10-raw-native-vendor.md').read_text().splitlines()
base = Path('/home/user/hermes-agent/native/fts5_cjk/vendor')
CITE = re.compile(r'`native/fts5_cjk/vendor/(sqlite3(?:ext)?\.h):(\d+)(?:-(\d+))?`')
i = checked = problems = 0
while i < len(note):
    m = CITE.search(note[i])
    if m:
        j = i + 1
        while j < len(note) and not note[j].strip():
            j += 1
        if j < len(note) and note[j].startswith('```'):
            body, k = [], j + 1
            while k < len(note) and not note[k].startswith('```'):
                body.append(note[k]); k += 1
            src = (base / m.group(1)).read_text().splitlines()
            start = int(m.group(2)); end = int(m.group(3) or m.group(2))
            def at(n):
                return src[n] if 0 <= n < len(src) else '<EOF>'
            bad = [(start + n, bl, at(start - 1 + n)) for n, bl in enumerate(body)
                   if ' '.join(bl.split()) != ' '.join(at(start - 1 + n).split())]
            rng_ok = end == start + len(body) - 1
            checked += 1; problems += len(bad) + (0 if rng_ok else 1)
            print('OK  ' if not bad and rng_ok else 'BAD ', m.group(0),
                  f'({len(body)} 行, 声明区间 {start}-{end}'
                  + ('' if rng_ok else ' <- 区间与块行数不符') + ')')
            for ln, mine, theirs in bad:
                print(f'   line {ln}\n    note: {mine}\n    base: {theirs}')
            i = k; continue
    i += 1
print(f'checked={checked} problems={problems}')
PY
```

---

## §9 移交

| 编号 | 锚点 + 现象 | 建议动作 |
|---|---|---|
| H-R10I-a | `scripts/assign_layers.py:623`:`("native/**", "L2", "R10"),` —— 这条目录级 catch-all(排在 619-622 那三条显式行之后)是把两个随附头文件判成 L2 的唯一原因;L4 的定义在同文件 `scripts/assign_layers.py:11`:`L4  有理由排除   — generated / vendored / binary / media / lockfiles; justified skip` 里字面写着 vendored | 本底稿即 §5.3 要求的"有理由排除"依据。请主线把 `data/ledger.tsv` 两行改 `L4` / `round=-` / `status=R10-vendored-justified-skip`,L2 减 14,498 行、L4 加 14,498 行,加总不变;`R1-inventoried` 剩余相应减 2 文件 / 14,498 行。**本片未改台账、未改脚本** |
| H-R10I-b | `tests/test_fts_cjk_bigram.py:28`:`f"-I{VENDOR}", str(SRC),` —— gcc 命令行无条件带 `-I<vendor>`,而 `native/fts5_cjk/README.md:11-12` 与 `native/fts5_cjk/build.sh:4-6` 都把 vendor 描述成"系统头缺失时的兜底";后果是 CI 编出的 `.so` 永远照 3.50.4 头编,与 runner 装没装 libsqlite3-dev 无关 | R11/R12 若写"构建与打包"章,这是「文档描述的是 A 路径、自动化走的是 B 路径」的一个短例子。◇1 已定案,无需重查 |
| H-R10I-c | `hermes_cli/managed_uv.py:440`:`every published 3.11.14 build links SQLite 3.50.4` —— 托管运行时的 SQLite 版本与 `vendor/sqlite3.h` 声明的版本是同一个数(3.50.4),但仓库里两处互不引用、也没有任何跟随检查 | 若后续轮读 `hermes_cli/managed_uv.py`(SQLite 运行时替换那一簇),把 `vendor/` 的版本一并纳入叙述:运行时一旦升到 3.53.1,随附头文件会静默留在 3.50.4。◇2 已定案 |
| H-R10I-d | **【R10B 已结清】** 本项目自己的工具口子:路径正则只认 `py md yaml yml toml c sh json ts tsx js` 十一种扩展、**不含 `h`**,于是**所有指向 `.h` 头文件的锚点既不计入 citations、也从不被比对**。本片 7 处 `.h` 锚点全部落在这个盲区里。同一条正则还会吃掉前导点,使 `.github/...` 一律解析不了(见 §4 跳 1′ 的注) | **R10B 开工杂项已修**(H-R10-a):白名单现为 `scripts/verify_citations.py:169`:`CITE_EXTS = "py\|mdx\|md\|yaml\|yml\|toml\|c\|h\|sh\|json\|tsx\|ts\|mjs\|js\|nix\|rs\|txt"`,并给正则加了可选前导点。**本片 13 处 `.h` 锚点已纳入校验并全绿**(本行原写"7 处"是本片自数,全语料实测 13 处)。行号锚点按当时口径写的 `:157` / `:158` 已随改动失效,故本行改为锚定符号名 |

---

## §10 交付自查(基线只读)

```verify
git -C /home/user/hermes-agent status --porcelain; echo "exit=$? (无输出 = 基线干净)"
git -C /home/user/hermes-agent rev-parse HEAD
```

`HEAD` = `863e31318553cda8ad61df681d08175364d4164b`,`status --porcelain` 无输出。
本片全部编译产物写在容器临时目录,未在基线内落任何文件;未装任何 Python 包。
