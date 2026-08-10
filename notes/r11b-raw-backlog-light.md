# r11b 片 B2 底稿 —— R2 / R4 / R6 / R8B 那 26 个 L1 文件的欠账清偿

> 本文是**证据层底稿**,求全求证,不求好读。凡对 hermes-agent 行为的断言,
> 锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前,代码块为逐字摘录。
> 基线:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`。

---

## 0. 本片是什么

`reports/round-9d-l1-completion.md` 点名了 **38 个 L1 文件在全部产出语料里没有任何一条可溯源断言**
——台账把它们标成了 `*-deep-read`,但没有任何一轮真的引用过它们的路径,`status` 高于实际交付。
其中 12 个(R7B 平台簇)交片 B1;**剩下 26 个(2,750 行)是本片**,准确清单取自
`data/r11b/backlog-38.tsv` 中 `round` 为 R2 / R4 / R6 / R8B 的行:

| 轮次 | 个数 | 行数 | 本文对应节 |
|---|---|---|---|
| R8B | 17 | 1,023 | §1 |
| R6 | 2 | 980 | §2 |
| R2 | 3 | 525 | §3 |
| R4 | 4 | 222 | §4 |
| 合计 | **26** | **2,750** | |

**口径纠正一处**:派工书 §片 B2 把 R8B 那 17 个列作
`backup claw console debug hooks import_cmd insights logs memory model plugins prompt_size skin slack tools uninstall webhook`,
其中 `model.py` 并不在 TSV 里(它已被覆盖),TSV 里的第 17 个是 **`whatsapp.py`**。
派工书自己写了「以 TSV 为准」,本文按 TSV 执行。

### 环境记录(报数即记环境)

```verify
echo "venv dist-info: $(ls -d /home/user/hermes-venv/lib/python*/site-packages/*.dist-info | wc -l)"
echo "pip list      : $(/home/user/hermes-venv/bin/pip list 2>/dev/null | tail -n +3 | wc -l)"
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import sys; sys.path.insert(0, '/home/user/hermes-agent')
from tools.lazy_deps import _allow_lazy_installs
print('_allow_lazy_installs =', _allow_lazy_installs())"
```

```text
venv dist-info: 87
pip list      : 87
_allow_lazy_installs = False
```

即 CLAUDE.md「惰性安装纪律」的封印**实测生效**,本片执行的任何基线代码都不会联网装包。

**一条给后续片的注意事项**:`scripts/run_tests.sh` 会往基线目录写 `test_durations.json`。
它在基线的 `.gitignore` 里(`.gitignore:35`),所以 `git status --porcelain` 仍为空、
`verify_ledger.py` 的「基线干净」检查照样通过——但**它确实在只读目录里落了文件**,
下一片若看到该文件出现,不必当作事故排查。

---

## 1. R8B:`hermes_cli/subcommands/` 那 17 个薄壳(1,023 行)

### 1.1 场景:为什么会有这么一层看起来什么都没干的壳

你敲 `hermes backup --quick`。argparse 要先知道 `backup` 这个子命令存在、
它接受 `-o/--output`、`-q/--quick`、`-l/--label` 三个参数,然后把解析出来的
`Namespace` 交给某个 `cmd_backup(args)` 去真干活。

问题在于:**这两件事的变化频率和依赖重量完全不同**。
「有哪些参数」是一张静态的表,纯 argparse,没有任何运行时依赖;
「干活」要 import 配置层、状态库、压缩库、凭据层。而 hermes 的 `cmd_*` 处理函数
**全部住在 `hermes_cli/main.py` 这个 12,599 行的巨文件里**。

于是任何想「只知道 CLI 长什么样、但不想真跑它」的人——比如要渲染一份命令清单的
Console REPL——都会被迫 import 那 12,599 行。这 17 个壳存在,就是为了把「表」从「活」里摘出来。

### 1.2 机制:注入式 builder

`hermes_cli/subcommands/__init__.py:3 @ 863e313`

```
``hermes_cli/main.py:main()`` historically built the entire argparse tree
inline — 179 ``add_parser`` calls across ~26 subcommand groups, all wedged
into one 3,300-line function. This package breaks that tree apart: each
subcommand group owns a ``build_<group>_parser(subparsers, ...)`` function in
its own module, and ``main()`` calls those builders instead of inlining the
argument definitions.
```

关键那一句在下一段:

`hermes_cli/subcommands/__init__.py:10 @ 863e313`

```
Handlers (the ``cmd_*`` functions) still live in ``main.py`` for now and are
dependency-injected into the builders so these modules never import ``main``
(which would create a cycle). Shared parser helpers live in
``_shared.py``.
```

**这就是这一层的全部设计**:壳只声明参数,处理函数由调用方**作为关键字参数注入**。
形态统一到了近乎模板的程度——17 个文件全部是
`def build_<X>_parser(subparsers, *, cmd_<X>: Callable) -> None:`,
函数体最后一句永远是 `..._parser.set_defaults(func=cmd_<X>)`。

`hermes_cli/subcommands/backup.py:12 @ 863e313`

```
def build_backup_parser(subparsers, *, cmd_backup: Callable) -> None:
    """Attach the ``backup`` subcommand to ``subparsers``."""
```

`hermes_cli/subcommands/backup.py:38 @ 863e313`

```
    backup_parser.set_defaults(func=cmd_backup)
```

`set_defaults(func=...)` 是 argparse 的标准把戏:把处理函数塞进解析结果的
`Namespace.func`,主循环只需 `args.func(args)`,不必知道分发表。
**注入 + set_defaults 合起来,让「谁来处理」这件事完全不出现在壳里。**

### 1.3 这层壳换来了什么:第二个消费者

如果 `main.py` 是唯一消费者,这层壳就只是文本搬家。真正的回报在于**它有第二个消费者**。

```verify
cd /home/user/hermes-agent && grep -rn "build_\(backup\|claw\|console\|debug\|hooks\|import_cmd\|insights\|logs\|memory\|plugins\|prompt_size\|skin\|slack\|tools\|uninstall\|webhook\|whatsapp\)_parser" --include=*.py . | grep -v '^\./hermes_cli/subcommands/' | sed 's/:.*//' | sort | uniq -c
```

```text
     11 ./hermes_cli/console_engine.py
     34 ./hermes_cli/main.py
      2 ./tests/hermes_cli/test_slack_cli.py
     20 ./tests/hermes_cli/test_subcommands_batch.py
     10 ./tests/hermes_cli/test_subcommands_followup.py
      3 ./tests/hermes_cli/test_uninstall_dry_run.py
```

**搜索面说明(负结论成本)**:模式为 17 个 builder 函数名的字面 grep,
范围是基线仓库全部 `*.py`(`grep -rn --include=*.py .`,含 `tests/`、`apps/`、
`optional-skills/` 等一切子树),排除的只有壳自身所在目录 `hermes_cli/subcommands/`。
结论「这 17 个 builder 的非测试消费者只有 `main.py` 与 `console_engine.py` 两个」
的可信度即等于这次 grep 的完备性;**未覆盖的形态是动态字符串拼接调用**
——而 `console_engine.py` 恰恰就是用字符串名调用的,所以它是被上面这条 grep
以「字符串字面量」形式命中的,不是漏网(见下)。

第二个消费者是 **Hermes Console**,一个「受策展的、不是裸 shell」的 REPL:

`hermes_cli/subcommands/console.py:13 @ 863e313`

```
        description=(
            "Open a curated Hermes command REPL. This is not a raw shell and "
            "does not expose the full Hermes CLI."
        ),
```

它要在每次连接时渲染一份「你能用哪些命令、每条是干什么的」清单。这份清单的文本
就是 argparse 里的 `help=` / `description=`。于是它把壳当**元数据源**用:

`hermes_cli/console_engine.py:215 @ 863e313`

```
# The CLI surface these helpers reflect is process-static: they import a
# subcommand module and build a throwaway argparse tree purely to extract help
# summaries. Nothing about the result changes across engine instances, but the
# dashboard opens a fresh HermesConsoleEngine per /api/console connection, so
# without memoization every reconnect re-imports + re-parses the whole surface.
# Cache by args (all hashable strings); callers only read the returned map.
@functools.lru_cache(maxsize=None)
def _extracted_summaries(
    module_name: str,
    builder_name: str,
    main_handler_name: str,
) -> dict[tuple[str, ...], str]:
    try:
        parser, subparsers = _parser_root()
        module = importlib.import_module(module_name)
        builder = getattr(module, builder_name)
        builder(subparsers, **{main_handler_name: _noop_console_command})
        return _summaries_from_parser(parser)
    except Exception:
        return {}
```

**`_noop_console_command` 是重点**:注入一个什么都不做的假处理函数,
就能建出一棵完整的 argparse 树、把 help 文本全抽出来,**而完全不 import `main.py`**。
壳的「注入」设计在这里第一次真正付钱。

而真的要**执行**时,才付那笔 import:

`hermes_cli/console_engine.py:302 @ 863e313`

```
    parser, subparsers = _parser_root()
    module = importlib.import_module(module_name)
    main_module = importlib.import_module("hermes_cli.main")
```

**取舍写清楚**:这不是「Console 永远不 import main」,而是
**「渲染清单不 import,执行才 import」**。清单在每次 `/api/console` 连接时都要渲染
(注释里那句 `the dashboard opens a fresh HermesConsoleEngine per /api/console connection`),
执行则是用户主动敲了一条命令才发生——**把高频路径和重依赖解开**,这就是这层壳的全部价值。
`lru_cache` 是同一动机的第二层:连 argparse 树本身都不重建。

### 1.4 十七个文件逐个的可溯源断言

下表每行的锚点后**紧跟反引号摘录**(声明式写法),因此会被 `verify_citations.py` 机械校验。

| 文件 | 行 | 断言(它在链路里解决什么) | 锚点 + 摘录 |
|---|---|---|---|
| `hermes_cli/subcommands/backup.py` | 38 | `--quick` 不是「快一点」,而是把「最小可恢复集」这个产品决定写死在 help 里:config、state.db、.env、auth、cron 五样。壳因此是这个决定的**唯一声明处** | `hermes_cli/subcommands/backup.py:33`:`help="Quick snapshot: only critical state files (config, state.db, .env, auth, cron)",` |
| `hermes_cli/subcommands/claw.py` | 92 | 从 OpenClaw 迁移**默认不搬密钥**;`--migrate-secrets` 是二次同意闸,连 `--preset full` 都不豁免。安全语义落在 argparse 层,处理函数无从绕过 | `hermes_cli/subcommands/claw.py:51`:`help="Include allowlisted secrets (TELEGRAM_BOT_TOKEN, API keys, etc.). "` |
| `hermes_cli/subcommands/console.py` | 18 | 17 个里参数最少的两个之一(0 个 `add_argument`);它注册的正是 §1.3 那个反过来消费其余壳的 REPL | `hermes_cli/subcommands/console.py:18`:`console_parser.set_defaults(func=cmd_console)` |
| `hermes_cli/subcommands/debug.py` | 100 | 17 个里仅有的两个 `import argparse` 之一,为了 `RawDescriptionHelpFormatter` + 多行 epilog 示例;`--no-redact` 的 help 把「默认脱敏、走 `agent.redact.redact_sensitive_text` 且 `force=True`」写进了命令行契约 | `hermes_cli/subcommands/debug.py:73`:`"Disable upload-time secret redaction (default: redact). Logs "` |
| `hermes_cli/subcommands/hooks.py` | 77 | shell hook 的「首次使用同意」名单落在 `~/.hermes/shell-hooks-allowlist.json`,`hooks revoke` 是它的唯一 CLI 出口;`hooks test` 用合成 payload 干跑,是 hook 这类「只有真事件才触发」的东西的可测性设计 | `hermes_cli/subcommands/hooks.py:21`:`"consent allowlist at ~/.hermes/shell-hooks-allowlist.json."` |
| `hermes_cli/subcommands/import_cmd.py` | 31 | **模块名被 Python 关键字逼歪的样本**:命令叫 `import`,但模块不能叫 `import.py`(`from ... import import` 是语法错),于是模块与 builder 都带 `_cmd` 后缀,而注入的处理函数仍叫 `cmd_import` | `hermes_cli/subcommands/import_cmd.py:12`:`def build_import_cmd_parser(subparsers, *, cmd_import: Callable) -> None:` |
| `hermes_cli/subcommands/insights.py` | 25 | 用量分析的窗口默认 30 天、可按平台过滤;壳把「分析多久」这个默认值钉在这里,`cmd_insights` 只读 `args.days` | `hermes_cli/subcommands/insights.py:20`:`"--days", type=int, default=30, help="Number of days to analyze (default: 30)"` |
| `hermes_cli/subcommands/logs.py` | 78 | 另一个 `import argparse` 的壳;它把「有哪几个日志文件」(agent / errors / gateway / gui / desktop)以位置参数默认值 `agent` 的形式固化,等于一份日志清单的声明 | `hermes_cli/subcommands/logs.py:22`:`formatter_class=argparse.RawDescriptionHelpFormatter,` |
| `hermes_cli/subcommands/memory.py` | 53 | 壳的 description 里**硬编码了一份 provider 名单**,而实际 provider 是目录扫描发现的 —— 已漂(见 §5 ■-B2-03) | `hermes_cli/subcommands/memory.py:19`:`"Available providers: honcho, openviking, mem0, hindsight,\n"` |
| `hermes_cli/subcommands/plugins.py` | 106 | 17 个里参数最多的(15 个 `add_argument`);`--enable` / `--no-enable` 用互斥组表达三态:给任一 = 跳过确认,都不给 = 走交互确认。同一手法再用于 `--allow-tool-override`(插件替换内置工具需显式授权) | `hermes_cli/subcommands/plugins.py:34`:`_install_enable_group = plugins_install.add_mutually_exclusive_group()` |
| `hermes_cli/subcommands/prompt_size.py` | 36 | 「新会话的固定 prompt 预算」离线核算入口,**不打 API**;这让 prompt 体积成为可在 CI 里回归的数,而不是只能靠账单发现 | `hermes_cli/subcommands/prompt_size.py:23`:`"JSON. Runs offline (no API call)."` |
| `hermes_cli/subcommands/skin.py` | 30 | 与 `console.py` 一样是**不带溯源注释**的两个壳之一(见 §1.5);`skin set` 的语义「就地改活动皮肤的一个颜色、背景不动」写在注释里而非 help | `hermes_cli/subcommands/skin.py:22`:`# skin set — change ONE color of the active skin in place (bg untouched).` |
| `hermes_cli/subcommands/slack.py` | 93 | `hermes slack manifest` 把 `COMMAND_REGISTRY` 渲染成 Slack app manifest;`--agent-view` 的 help 明说这次切换**在 Slack 侧不可逆**——把不可逆性写进 help,是壳层能做的最强防呆 | `hermes_cli/subcommands/slack.py:90`:`"experience. This changes Slack's app messaging surface and cannot "` |
| `hermes_cli/subcommands/tools.py` | 95 | `tools post-setup <key>` 把「装后端依赖」从交互向导里拆成**稳定的非交互入口**,给 dashboard 调用;9 个 key 直接列在 description 里 | `hermes_cli/subcommands/tools.py:80`:`"Run the install/bootstrap hook a tool backend declares — the\n"` |
| `hermes_cli/subcommands/uninstall.py` | 46 | `--gui-summary` 输出 JSON 后即退出,是给桌面 app 用来**决定卸载对话框显示哪些选项**的探针;卸载器同时是自己的能力查询接口 | `hermes_cli/subcommands/uninstall.py:35`:`help="Print a JSON summary of installed GUI/agent artifacts and exit "` |
| `hermes_cli/subcommands/webhook.py` | 83 | `--script` 定义了 webhook 的过滤/改写钩子协议:payload 走 stdin,**空 stdout / `[SILENT]` / 非零退出码都表示忽略本次 webhook**。三种「忽略」信号写在 help 里,是这条协议的唯一规格 | `hermes_cli/subcommands/webhook.py:61`:`help="Filter/transform script under ~/.hermes/scripts/. The route "` |
| `hermes_cli/subcommands/whatsapp.py` | 22 | 参数最少的两个之一(0 个 `add_argument`),纯转发:全部配置由 `cmd_whatsapp` 的向导拥有。它证明这一层的下限就是「只声明命令名 + 注入处理函数」 | `hermes_cli/subcommands/whatsapp.py:22`:`whatsapp_parser.set_defaults(func=cmd_whatsapp)` |

形态数据(用来支撑上表里「最多/最少/唯二」这几个说法):

```verify
cd /home/user/hermes-agent && for f in backup claw console debug hooks import_cmd insights logs memory plugins prompt_size skin slack tools uninstall webhook whatsapp; do printf "%-12s add_argument=%-3s add_parser=%s\n" "$f" "$(grep -c "add_argument(" hermes_cli/subcommands/$f.py)" "$(grep -c "add_parser(" hermes_cli/subcommands/$f.py)"; done
```

```text
backup       add_argument=3   add_parser=1
claw         add_argument=12  add_parser=3
console      add_argument=0   add_parser=1
debug        add_argument=7   add_parser=3
hooks        add_argument=4   add_parser=5
import_cmd   add_argument=2   add_parser=1
insights     add_argument=2   add_parser=1
logs         add_argument=7   add_parser=1
memory       add_argument=3   add_parser=5
plugins      add_argument=15  add_parser=7
prompt_size  add_argument=2   add_parser=1
skin         add_argument=4   add_parser=4
slack        add_argument=8   add_parser=2
tools        add_argument=7   add_parser=5
uninstall    add_argument=5   add_parser=1
webhook      add_argument=13  add_parser=5
whatsapp     add_argument=0   add_parser=1
```

### 1.5 形态与其他不同的那几个

**(a) 两个没有溯源注释的壳。** 15 个壳的 docstring 第 3 行是同一句
`Extracted verbatim from ...` 或 `Extracted from ... (god-file Phase 2 follow-up)`;
只有 `console.py` 与 `skin.py` 是单行 docstring、没有溯源句。

`hermes_cli/subcommands/console.py:1 @ 863e313`

```
"""``hermes console`` subcommand parser."""
```

这两个是**新写的命令**(不是从 `main.py` 搬出来的),所以没有「从哪搬来」可写。
一句 docstring 的有无,如实记录了这一层里哪些是搬迁产物、哪些是新生。

**(b) 两批搬迁。** 溯源句本身分两种:`Phase 2`(10 个,含 `Extracted verbatim`)
与 `Phase 2 follow-up`(5 个:`claw` `insights` `memory` `plugins` `tools`)。
后者五个恰好也是**没有 `verbatim` 字样**的五个——即作者明说这批不是逐字搬,而是重写过。

**(c) 唯二 import argparse 的壳。** `debug.py:9` 与 `logs.py:9`,都是为了
`RawDescriptionHelpFormatter` + 多行 epilog。其余 15 个只 import `typing.Callable`。
**一个壳一旦需要 import argparse,就说明它带了「展示形态」的决定,不再是纯声明。**

**(d) 参数最少 / 最多**:`console.py` 与 `whatsapp.py` 各 0 个 `add_argument`(纯转发),
`plugins.py` 15 个、`webhook.py` 13 个、`claw.py` 12 个(三个真有子命令树的)。

### 1.6 这层壳没做完:一半的树还在 `main.py` 里

`hermes_cli/subcommands/__init__.py:3` 那段说「each subcommand group owns a
`build_<group>_parser`」。**实测不成立**:

```verify
cd /home/user/hermes-agent && printf 'builder modules: %s\n' "$(grep -l '^def build_.*_parser' hermes_cli/subcommands/*.py | wc -l)" && printf 'root groups still inline in main(): %s\n' "$(awk 'NR>=11183' hermes_cli/main.py | grep -cE '^ +([a-z_]+ = )?subparsers\.add_parser\(')"
```

```text
builder modules: 42
root groups still inline in main(): 16
```

`main()` 从 `hermes_cli/main.py:11183` 到文件末(12,599 行),里面仍有 **16 个顶层命令组**
直接内联 `subparsers.add_parser(`(`sessions`、`moa`、`fallback`、`secrets`、`egress`、
`migrate`、`checkpoints`、`bundles`、`curator`、`pets`、`journey`、`computer-use`、
`whatsapp-cloud`、`completion` 等)。见 §5 的 **▲-B2-01**。

*判定口径*:`grep -cE '^ +([a-z_]+ = )?subparsers\.add_parser\('` 只数**缩进的、
以 `subparsers`(根 subparsers 对象)为接收者**的调用,因此不含子命令的二级
`xxx_subparsers.add_parser(`,也不含 `hermes_cli/main.py:10600` 那条提到该调用形状的注释。
**16 这个数是「顶层命令组」的数,不是 `add_parser` 调用总数。**

---

## 2. R6:Honcho 的两个重文件(980 行)

R6 成品章(`chapters/r6-memory-provider-ecosystem.md`)讲了统一插口、三档写路径、
读路径单槽缓存、防自污染,以及 §3.8 的 **MCP** OAuth。
**这两个文件都不在其中**:一个是记忆 provider 的「声明式配置面」,
一个是**同一仓库里的第二套 OAuth 客户端**——而它的设计选择与 §3.8 那条
「客户端侧 OAuth 不要自己写协议」的可迁移原则**恰好相反**。

### 2.1 `plugins/memory/honcho/config_schema.py`(324 行)——把配置面声明成数据

#### 场景

用户在桌面 app 里点开「记忆 → Honcho」面板,看到一排输入框:API key、Base URL、
Workspace、Session strategy……每个都有标签、占位符、下拉选项、分组。
八个记忆 provider 各有各的配置面。要不要给每个 provider 写一套 UI 组件?

#### 设计:每个 provider 声明一张表,渲染器只有一个

`plugins/memory/config_schema.py:3 @ 863e313`

```
Each memory provider plugin *declares* its configurable surface in a
``config_schema.py`` next to its ``__init__.py`` — the fields, their types,
which values are secrets, and (for selects) the allowed options. A single
generic renderer in the desktop UI and a single generic ``GET/PUT
/api/memory/providers/{name}/config`` endpoint pair drive the whole
experience, so adding a provider config surface is pure declaration with no
bespoke UI components.
```

Honcho 的那张表就是本文件,开头一行 docstring 说明了它的身份:

`plugins/memory/honcho/config_schema.py:1 @ 863e313`

```
"""Honcho's declared config surface — rendered by the generic desktop panel."""
```

`plugins/memory/honcho/config_schema.py:27 @ 863e313`

```
CONFIG_SCHEMA = ProviderConfigSchema(
    name="honcho",
    label="Honcho",
    storage=STORAGE_HONCHO_HOST_BLOCK,
    docs_url="https://docs.honcho.dev/v3/guides/integrations/hermes",
    fields=(
```

`storage=STORAGE_HONCHO_HOST_BLOCK` 是这张表里唯一「非纯 UI」的字段:
它告诉通用读写端点**这个 provider 的配置落在哪种存储形状里**
(Honcho 是 `honcho.json` 的 per-host 块,其他 provider 走扁平 JSON)。
**声明式表里带一个 storage 判别标签,是「一个渲染器打天下」能成立的前提。**

#### 关键约束:按路径加载,永不 import 包

`plugins/memory/config_schema.py:11 @ 863e313`

```
Schema files are loaded by path (like the provider plugins themselves), never
via package import: plugin ``__init__.py`` files pull in the agent runtime,
which must not load into the web server. A ``config_schema.py`` may only
import from this module.
```

`plugins/memory/config_schema.py:132 @ 863e313`

```
    try:
        spec = importlib.util.spec_from_file_location(f"_hermes_memory_config_schema.{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema = getattr(module, "CONFIG_SCHEMA", None)
```

**这是本文件之所以是一个单独文件、而不是 provider `__init__.py` 里一个常量的全部原因。**
`plugins/memory/honcho/__init__.py` 有 1,550 行、会把 agent 运行时拖进来;
web server 进程不能承受这个。于是配置面被切成一个**只许 import 上游那一个模块**的叶子文件,
用 `spec_from_file_location` 直接执行文件本身。Honcho 这张表严格遵守了这条约束——
它的 import 只有一处,就是 `plugins.memory.config_schema`(见文件 `:3`)。

*代价*:`config_schema.py` 与真正读配置的代码(`client.py` / `session.py`)之间
**没有任何编译期联系**,只有键名字符串对得上才生效。这正是 r6 章 §5
「一个拼错了却不报错的键名」那类风险的结构性来源。本片做了一次对齐检查(见 §5 ◎-B2-01)。

#### inline / full 两档

`plugins/memory/honcho/config_schema.py:118 @ 863e313`

```
        # —————— Full-config-only fields below (inline=False) ——————
```

前 7 个字段带 `inline=True`(紧凑面板里直接可见),其后 21 个只在「完整配置」弹窗里出现,
并用 `group=` 分成 Connection / Identity / Session / Message writing / Dialectic /
Reasoning / Recall / Limits / Observation 九组。
**「哪几个是常用的」这个产品判断也被声明成了数据**,而不是写在 UI 组件里。

### 2.2 `plugins/memory/honcho/oauth_flow.py`(656 行)——仓库里第二套 OAuth 客户端

#### 场景

用户跑 `hermes honcho setup`。以前只有一条路:去 app.honcho.dev 复制一个 API key 粘回来。
现在向导会问 `oauth, device, or apikey?`,默认 `oauth`——浏览器弹出授权页,
点同意,标签页显示「可以关掉了」,终端里 token 已经存好。
如果你是 SSH 进一台没有浏览器的机器,它会改推 `device`:终端打一串短码,
你在**任何一台**有浏览器的设备上输入这串码批准。

#### 这个文件在链路里的位置

`plugins/memory/honcho/oauth_flow.py:1 @ 863e313`

```
"""Browser sign-in flow for the Honcho memory provider — no CLI step.

``begin_authorization`` / ``complete_authorization`` are the transport-agnostic
core: the code can arrive via the loopback listener here or a future
``hermes://`` handler. Endpoints are env-overridable with local-dev defaults
because ``/authorize`` (dashboard) and ``/oauth/token`` (API) live on
different origins.
"""
```

三个入口,三种宿主:

| 入口 | 调用方 | 形态 |
|---|---|---|
| `authorize_via_loopback` | `plugins/memory/honcho/cli.py:722`:`from plugins.memory.honcho.oauth_flow import authorize_via_loopback` | CLI 向导,阻塞等浏览器回调 |
| `authorize_via_device_code` | `plugins/memory/honcho/cli.py:660`:`from plugins.memory.honcho.oauth_flow import (` | CLI 向导的无浏览器分支 |
| `start_loopback_flow_background` | `hermes_cli/memory_oauth.py:66`:`return flow.start_loopback_flow_background()` | 桌面 dashboard 的「Connect」按钮 |

第三个入口的接法值得单说——它是**按约定分发**的,provider 名字不出现在路由层:

`hermes_cli/memory_oauth.py:1 @ 863e313`

```
"""HTTP routes for memory-provider OAuth connect, mounted by ``web_server``.

Kept out of ``web_server.py`` so the memory feature's surface stays in the
memory layer. Dispatch is by convention: a provider's flow lives at
``plugins.memory.<provider>.oauth_flow`` exposing ``start_loopback_flow_background``
and ``get_flow_status``; a provider without that module simply 404s. No provider
is named here.
"""
```

**「有这个模块 + 有这两个函数 = 你支持 OAuth 连接」**,没有注册表、没有 if/else。
本文件末尾那两个函数因此不是内部工具,而是**一份跨 provider 的鸭子类型契约的实现**。

#### 设计逐条(每条都能单独搬走)

**(1) 回调地址写死 IP 字面量,不写 `localhost`。**

`plugins/memory/honcho/oauth_flow.py:30 @ 863e313`

```
# The loopback redirect registered for the Hermes OAuth client. IP-literal so
# the browser can't resolve the advertised host to ::1 and miss the IPv4 bind.
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PORT = 8765
LOOPBACK_REDIRECT_URI = f"http://{LOOPBACK_HOST}:{LOOPBACK_PORT}/callback"
```

这是一类真实故障:服务端 bind 了 IPv4,浏览器把 `localhost` 解析成 `::1`,回调打不进来,
用户看到的现象是「点了同意,终端一直在等」。**双栈环境里 `localhost` 不是一个地址,是一个选择。**

**(2) 先 bind 再宣告端口。**

`plugins/memory/honcho/oauth_flow.py:343 @ 863e313`

```
    # Bind first so the advertised redirect_uri carries the actual bound port
    # (which may differ from :8765 if it was taken).
    server, captured = _bind_loopback_server()
    redirect_uri = f"http://{LOOPBACK_HOST}:{server.server_address[1]}/callback"
```

`_bind_loopback_server` 先试 8765,`OSError` 就退到 `(LOOPBACK_HOST, 0)` 让内核派端口
(`plugins/memory/honcho/oauth_flow.py:293-297`)。因为**先 bind 后取 `server_address[1]`**,
「探测端口 → 释放 → 稍后再 bind」那个 TOCTOU 窗口根本不存在。
这与 r6 章 §3.8 记的 MCP 侧「预留即持有」是同一条原则的两种写法。

**(3) 浏览器在另一个线程开,socket 已经 bind 好了。**

`plugins/memory/honcho/oauth_flow.py:359 @ 863e313`

```
    # Browser opens from a short-lived thread; the socket is already bound, so a
    # fast redirect can't beat it.
    opener = threading.Thread(target=lambda: open_url(authorize_url), daemon=True)
    opener.start()
```

**(4) 等回调的循环不认错门。**

`plugins/memory/honcho/oauth_flow.py:310 @ 863e313`

```
        # handle_request honors server.timeout; loop until our callback lands so a
        # stray probe to another path doesn't end the wait empty-handed.
        deadline = time.monotonic() + timeout
        while "code" not in captured and time.monotonic() < deadline:
            server.handle_request()
```

`HTTPServer.handle_request()` 处理**一个**请求就返回。浏览器扩展、`/favicon.ico`、
局域网扫描器随便打一发,都会让「只调一次 handle_request」的写法空手而归。
所以循环条件是 `"code" not in captured`,不是「处理过一个请求」。

**(5) PKCE 手写,S256。**

`plugins/memory/honcho/oauth_flow.py:134 @ 863e313`

```
def _pkce() -> tuple[str, str]:
    """Return (verifier, S256 challenge) for an authorization-code request."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge
```

**(6) CSRF:pending 表按 `state` 键控,回来时对比。**

`plugins/memory/honcho/oauth_flow.py:36 @ 863e313`

```
# Pending authorizations live only until their callback returns; keyed by the
# CSRF ``state`` so a stray/forged callback can't complete a grant.
_PENDING_TTL_SECONDS = 600
```

`plugins/memory/honcho/oauth_flow.py:364 @ 863e313`

```
    code, returned_state = capture_loopback_code(server, captured, timeout=timeout)
    if returned_state != state:
        raise ValueError("OAuth state mismatch — possible CSRF, aborting")
```

注意这里**校验了两次**:`complete_authorization` 里 `_pending.pop(state)` 拿不到就抛
`unknown or expired authorization state`(`:204-207`),
而 `authorize_via_loopback` 在调它之前先自己比了一次。
两道都在,是因为 `complete_authorization` 是「传输无关的核」,
将来 `hermes://` handler 也会调它——**核自己必须能守住,不能假定调用方守过**。
*(与 r6 章 §3.8 的 MCP 侧不同:那边 state 由 SDK 生成并常量时间比对,
这里是 `!=` 直接比。对 CSRF state 这种「猜中即完成授权」的值,
常量时间比较是更保守的写法;本文件没有这么做——但 state 是 `secrets.token_urlsafe(32)`
且失败即抛,时序侧信道在这条链路上不构成可利用面,记录差异不判缺陷。)*

**(7) 同意页上不泄露绝对路径。**

`plugins/memory/honcho/oauth_flow.py:41 @ 863e313`

```
def _display_config_path(path: object) -> str:
    """Home-relative display string for the consent screen.

    The absolute path (username + home layout) never leaves the machine — it's
    only shown to the user. Collapse ``$HOME`` to ``~``; for a path outside
    home, send the bare filename rather than leak an arbitrary absolute path.
    """
```

授权链接带一个 `config_path` 参数,让同意页告诉用户「批准后会写到哪」。
但这个值**会离开本机**(它是 URL 的一部分)。于是:home 内折成 `~/…`,
home 外只送 basename。**一个纯 UX 字段被当作数据出境点对待。**

**(8) 设备码流(RFC 8628)是为「浏览器不在这台机器上」准备的。**

`plugins/memory/honcho/oauth_flow.py:377 @ 863e313`

```
# — Device authorization grant (RFC 8628), for headless / remote-VM clients —
# The loopback flow needs the browser on the same machine; here the CLI prints
# a short user code, the user approves from any browser (dashboard /device),
# and the device polls the token endpoint until the grant lands.
```

它的三处细节:

`plugins/memory/honcho/oauth_flow.py:384 @ 863e313`

```
# RFC 8628 §3.5: slow_down adds 5s per response; cap matches the server's
# DEVICE_POLL_INTERVAL_MAX so a misbehaving clock can't inflate past it.
_SLOW_DOWN_STEP = 5
_POLL_INTERVAL_CAP = 60
```

`plugins/memory/honcho/oauth_flow.py:427 @ 863e313`

```
def supports_device_login(endpoints: OAuthEndpoints, *, timeout: float = 5.0) -> bool:
    """Whether the host advertises the device grant in its RFC 8414 metadata.

    Fails closed: any connection error, non-200, or missing capability returns
    False, so hosts without the device grant simply don't offer the option.
    """
```

`plugins/memory/honcho/oauth_flow.py:514 @ 863e313`

```
        except httpx.TransportError as e:
            # A network blip mid-poll shouldn't kill a 10-minute wait.
            logger.debug("device token poll transport error, retrying: %s", e)
            continue
```

**这三条合起来是一套完整的「长轮询礼仪」**:能力探测 fail-closed(探不到就不给用户
看见这个选项,而不是给了再失败)、服务端的 `slow_down` 要听但要封顶、
网络抖动不能毁掉一次十分钟的等待。轮询的终局分支把 RFC 的四个错误码
映射成四个异常类(`AccessDenied` / `DeviceCodeExpired` / `AuthorizationTimeout` /
`DeviceFlowError`),CLI 侧因此能给出四种不同的人话(`plugins/memory/honcho/cli.py:693-711`)。

**(9) 后台启动:幂等 + 提前解析 profile 作用域。**

`plugins/memory/honcho/oauth_flow.py:636 @ 863e313`

```
    global _flow_thread
    # Resolve under the caller's profile scope NOW — the worker thread outlives
    # the request, where a context-local HERMES_HOME override can't reach.
    config_path = config_path or resolve_config_path()
    host = host or resolve_active_host()
    with _status_lock:
        if _status.state == "pending" and _flow_thread and _flow_thread.is_alive():
            return {"state": _status.state, "detail": _status.detail}
```

两个坑各堵一个:**(i)** 双击 Connect 按钮不能开两个浏览器标签页 / 抢两次 8765;
**(ii)** 工作线程比 HTTP 请求活得久,而 profile 作用域(`HERMES_HOME`)是
**context-local** 的——线程里再去 resolve 就解析到默认 profile 了。
所以在请求线程里先把 `config_path` / `host` 定死,再交给线程。
**「谁的 profile」必须在跨线程边界之前固化**,这条对任何有 per-profile 状态的
后台任务都成立。

#### 取舍:同一个仓库,两套 OAuth 客户端,两种相反的选择

r6 章 §3.8 的可迁移原则第一句是「客户端侧 OAuth 不要自己写协议,选一个实现了完整链的 SDK」。
**Honcho 这条路恰恰是手写的**:PKCE、state、loopback、设备码轮询、AS metadata 探测,
一行不假手 SDK。两者的差别不是谁对谁错,而是**问题不同**:

| | MCP OAuth(r6 章 §3.8) | Honcho OAuth(本文件) |
|---|---|---|
| 对手方 | **任意**第三方 MCP server | **一家**已知的授权服务器 |
| 需要 | 发现 + 动态客户端注册(DCR)+ 各家的坑 | 固定 client_id、固定两个端点 |
| 结论 | 全托 SDK,自己只做存储/回调/生命周期 | 手写 656 行,换来无 SDK 依赖 + 设备码流 |

`plugins/memory/honcho/oauth_flow.py:74 @ 863e313`

```
# One OAuth client for every surface. Consent branding/UI adapt via the
# ``source`` query param (not a separate client_id), so there's a single grant
# identity to refresh — no clientId-vs-refresh-token desync to revoke the grant.
_DEFAULT_CLIENT_ID = "hermes-agent"
```

**「一个 client_id 打所有入口,靠 `source` 参数区分品牌」这个决定,正是手写路线成立的前提**:
没有 DCR、没有多份注册信息,也就没有 MCP 侧那个 `invalid_client` 自愈逻辑要写。
可迁移的判据因此可以写得更准:**对手方是「一家」还是「任意一家」,决定你该手写还是该全托。**

---

## 3. R2:三个文件(525 行)—— 推理模型的超时地板

R2 成品章(`chapters/r2-turn-loop-and-model-access.md`)§3.6 讲了「一个分类器,四个恢复开关」,
§3.3 讲了「为什么永远用流式」。这三个文件是那两节底下**没被讲到的那一层**:
一张 30 行的静态表,和它撑起的四个决策点。

### 3.1 `agent/reasoning_timeouts.py`(231 行)—— 一张表,四个消费者

#### 场景

你让 Nemotron 3 Ultra 干一件复杂的事。它开始「想」——推理模型在吐出第一个正文 token 之前
会先产出一大段思考块,这段可能持续两三分钟。而 hermes 的流式停滞检测器默认 180 秒没动静
就判定连接死了,把它掐掉。用户看到的是 `BrokenPipeError`。

`agent/reasoning_timeouts.py:1 @ 863e313`

```
"""Per-reasoning-model stale-timeout floor for known reasoning models.

Reasoning models (those that emit extended thinking blocks before their
first content token) routinely exceed Hermes's default chat-model
stale detectors:

* Stream stale detector:   ``HERMES_STREAM_STALE_TIMEOUT``     default 180s
                           ``agent/chat_completion_helpers.py:2544``
* Non-stream stale detector: ``HERMES_API_CALL_STALE_TIMEOUT``  default 90s
                           ``run_agent.py:1140``
```

#### 设计:是**地板**,不是覆盖

`agent/reasoning_timeouts.py:22 @ 863e313`

```
This module provides a floor that the existing stale-detector scaling
blocks consult via :func:`get_reasoning_stale_timeout_floor` and
apply as ``max(default, floor)``. It is a FLOOR:
```

这个「地板」语义的三条边界写在紧随其后的三点里:不覆盖用户显式配置、
不降低已有阈值、对非推理模型零影响(不在名单里就返回 `None`)。
**一个只能往上抬、不能往下压的旋钮,是「自动缓解」这类功能能安全发货的形状。**

#### 匹配:起始锚 + 分隔符右锚 + 最长优先

表是 30 条 `(slug, floor_seconds)`(`:62-126`),从 `nemotron-3-ultra` 600 秒到
`grok-4-fast-non-reasoning` 180 秒。匹配规则:

`agent/reasoning_timeouts.py:155 @ 863e313`

```
_SORTED_REASONING_FLOORS: list[tuple[str, float, re.Pattern[str]]] = [
    (slug, floor, re.compile(r"^" + re.escape(slug) + r"(?:$|[\-._])"))
    for slug, floor in sorted(
        _REASONING_STALE_TIMEOUT_FLOORS, key=lambda kv: -len(kv[0])
    )
]
```

三个决定挤在这五行里:

- **`^` 起始锚**:`olmo-1` 不会匹配 `o1`,`llama-4-70b-o1-preview` 不会被误判成推理模型。
  文件 `:41-48` 专门用后者举例说明「子串 + 尾连字符」的旧写法为什么会过匹配。
- **`(?:$|[\-._])` 右锚**:`o3-mini` 能匹配 `o3-mini` 也能匹配 `o3-mini-2025-01-31`。
- **按 slug 长度降序排**:于是 `openai/o3-mini` 命中 `o3-mini`(300s)而不是先撞上 `o3`(600s)。
  **表的书写顺序因此可以随便**,`:60-61` 的注释明说 "Order is irrelevant"。

聚合器前缀在**进正则之前**就被剥掉:

`agent/reasoning_timeouts.py:226 @ 863e313`

```
    # Strip aggregator prefix (everything before and including the
    # last ``/``).  The wrapper regex anchors at start-of-string, so
    # the slug identity is the bare model name.
    if "/" in name:
        name = name.rsplit("/", 1)[1]
    return _match_any(name)
```

#### 四个消费者:一张表决定了四件事

| 消费点 | 位置 | 它决定什么 |
|---|---|---|
| 流式停滞阈值 | `agent/chat_completion_helpers.py:378`:`_reasoning_floor = get_reasoning_stale_timeout_floor(_model_id)` | `max(上下文缩放后的值, floor)` |
| Bedrock 变体 | `agent/chat_completion_helpers.py:445`:`floor = get_reasoning_stale_timeout_floor(cand)` | 把 `us.anthropic.claude-opus-4-6-v1:0` 归一成 slug 再查表 |
| 非流式停滞阈值 | `run_agent.py:1421`:`from agent.reasoning_timeouts import get_reasoning_stale_timeout_floor` | 命中即 `return reasoning_floor, False`,并关掉「本地端点免检」短路 |
| **错误分类** | `agent/error_classifier.py:956`:`if get_reasoning_stale_timeout_floor(model) is not None:` | 把断连从 `context_overflow` 改判为 `timeout` |

第四个是最重的,值得展开。

#### 这张表最贵的用途:拦住一次会删历史的误判

`agent/error_classifier.py:943 @ 863e313`

```
        # branch (should_compress=True) and silently delete
        # conversation history on a phantom context-length error.
```

`agent/error_classifier.py:955 @ 863e313`

```
        from agent.reasoning_timeouts import get_reasoning_stale_timeout_floor
        if get_reasoning_stale_timeout_floor(model) is not None:
            return _result(FailoverReason.timeout, retryable=True)
```

如果这一句不命中,控制流就往下走到:

`agent/error_classifier.py:961 @ 863e313`

```
        is_large = approx_tokens > context_length * 0.6 or (
            context_length <= 256000 and (approx_tokens > 120000 or num_messages > 200)
        )
        if is_large:
            return _result(
                FailoverReason.context_overflow,
                retryable=True,
                should_compress=True,
            )
```

**因果链讲成一句话**:推理模型在长会话里思考超时被上游掐断 → 分类器看到「断连 + 大会话」
→ 判成上下文溢出 → `should_compress=True` → **压缩掉对话历史**。
用户丢的是历史,而真实原因只是模型想得久了一点。

**这条链的开关就是那张 30 行的表。** 一个不在表里的新推理模型,
不只是「超时短一点」,而是**在长会话里踩到静默删历史**。
可迁移的教训:**当一张静态名单成为破坏性分支的唯一守门人时,
「不在名单里」的代价必须写进名单文件本身**——本文件的 docstring 做了这件事(`:22-31`),
但它没有任何机制保证新模型上架时有人来加行。

### 3.2 `agent/thinking_timeout_guidance.py`(136 行)—— 让报错说对话

#### 场景

同一个故障,用户看到的文案是:「试试用 execute_code 加 Python 的 open() 来写大文件」。
这是给「写大文件时流断了」准备的建议,对着一个思考超时的推理模型完全是胡说。

`agent/thinking_timeout_guidance.py:19 @ 863e313`

```
The existing `_is_stream_drop` guidance at
``agent/conversation_loop.py:3464-3486`` fires for large-file-write
stream drops ("try execute_code with Python's open() for large files")
which is the WRONG advice for the thinking-timeout case.  This module
provides the detection and the message as standalone helpers so the
detection logic is unit-testable without driving the full retry loop,
and the message text can be regression-tested for spelling and accuracy.
```

#### 设计:四个与条件,第三个就是那张表

`agent/thinking_timeout_guidance.py:41 @ 863e313`

```
_THINKING_TIMEOUT_SUBSTRINGS: tuple[str, ...] = (
    "broken pipe",
    "errno 32",
    "remote protocol",
    "connection reset",
    "connection lost",
    "peer closed",
    "server disconnected",
)
```

`agent/thinking_timeout_guidance.py:95 @ 863e313`

```
    # Condition 3: reasoning model allowlist.
    if get_reasoning_stale_timeout_floor(model) is None:
        return False
```

四条与:分类器判 timeout、没有 HTTP 状态码(是传输层断,不是 API 报错)、
模型在推理名单里、错误串命中传输 kill 特征。**只要有一条不成立就不给这段文案**
——错误建议比没有建议更贵。

#### 一个刻意的解耦

`agent/thinking_timeout_guidance.py:82 @ 863e313`

```
    # Condition 1: classifier says timeout.  Use a string/value check
    # rather than importing FailoverReason so this module has zero
    # import cycles from the error_classifier package.
    reason = getattr(classified, "reason", None)
    reason_value = getattr(reason, "value", None)
    if reason_value != "timeout":
        return False
```

它**鸭子类型地**读 `classified.reason.value`,不 import `FailoverReason`。
代价是丢掉了枚举的类型检查,换来的是这个模块可以被单元测试直接驱动。
文件顶端的 docstring 明说了这就是拆出来的目的("so the detection logic is
unit-testable without driving the full retry loop")。
**「这段判断值得单独测」本身就是拆模块的正当理由**,不必等到它被复用。

生成的文案给出三条按优先级排的自救(`:121-136`),第一条是可复制粘贴的 YAML 片段:
`providers.{provider}.models.{model}.stale_timeout_seconds: 900`,
并顺带告诉用户内置地板是 600s——**「如果你抬了还不行,说明上游的墙更矮」**。

### 3.3 `agent/oneshot.py`(158 行)—— 会话之外的一次性模型调用

#### 先排除一个同名陷阱

基线里有**两个** `oneshot.py`、**两个** `run_oneshot`:

| 路径 | 是什么 | 覆盖情况 |
|---|---|---|
| `hermes_cli/oneshot.py:170`:`def run_oneshot(` | `hermes -z` 一次性 CLI 模式(502 行),默认开 `HERMES_YOLO_MODE=1` | R8D 已精读(`notes/r8d-str-setup-and-ux.md`) |
| `agent/oneshot.py:106`:`def run_oneshot(` | 本节的对象:会话外的单次 LLM 请求(158 行) | **从未被引用过** |

**这大概就是它落进欠账的原因**:任何以 `oneshot` 为线索的搜索都会先命中
R8D 已经写过的那一个,痕迹看起来是全的。这正是 CLAUDE.md「不写裸文件名」
那条规矩要防的形态——`oneshot.py` 在基线里有两个候选,而它们语义无关。

#### 场景

桌面 app 里点「生成 commit message」。这需要一次模型调用。但它**不能**变成一个 agent turn:

`agent/oneshot.py:1 @ 863e313`

```
"""Shared one-off LLM requests for non-conversational helpers.

A "one-shot" is a single, stateless model call that runs *outside* any
conversation: it never touches a session's history, never breaks prompt
caching, and returns plain text. UI surfaces use it for small generative
chores — a commit message from a diff, a rename suggestion, a summary —
where spinning up an agent turn would be wrong (it would pollute the thread)
and hand-rolling an LLM call at every call site would be worse.
```

**两句话把设计约束讲完了**:走 agent turn 会污染会话历史、破坏 prompt cache
(R2 章 §3.8 讲的那条「字节稳定」命脉);每个调用点自己拼 LLM 调用则会散落
provider 分流、超时、凭据这些逻辑。中间这条路就是本模块。

唯一的非测试调用方是 `tui_gateway/methods_session.py:1110`:`from agent.oneshot import run_oneshot`。

#### 设计:模板是可调用对象,不是格式串

`agent/oneshot.py:31 @ 863e313`

```
# A template turns a variables dict into a (instructions, user_input) pair.
# Templates are plain callables (not str.format) so diff/code payloads with
# literal "{" / "}" pass through untouched.
PromptTemplate = Callable[[Dict[str, Any]], Tuple[str, str]]
```

**这条是被真实数据逼出来的**:一次性调用的载荷几乎总是 diff 或代码,
而代码里到处是 `{` `}`。用 `str.format` 的模板会在遇到 `{` 时炸或吞字符。
改成「模板 = 一个函数」,载荷就只是普通参数,永远不参与格式解析。

#### 一个很小但很典型的细节:重新生成

`agent/oneshot.py:72 @ 863e313`

```
    # "Regenerate" must yield something new even on models that decode greedily
    # / pin temperature server-side. A trailing nonce isn't enough, so we hand
    # back the previous message and require a genuinely different one.
    avoid = _truncate(str(variables.get("avoid") or "").strip(), 1000)
```

用户点「换一个」。如果模型服务端锁了 temperature、或者贪心解码,同样的 prompt
必然出同样的结果;加个随机后缀也没用(它不改变语义)。
**唯一可靠的办法是把上一版发回去,明确要求不同的一版。**
这是「让模型做非确定性动作」的通用配方。

出口做了一次防御性清洗:

`agent/oneshot.py:151 @ 863e313`

```
def _strip_code_fence(text: str) -> str:
```

模型经常给纯文本答案裹一层围栏。剥掉一层、且只剥完整包裹的一层
(首行以围栏起、末行恰好是围栏),否则原样返回。

输入侧则是硬截断:diff 12,000 字符、近期 commit 1,500 字符、avoid 1,000 字符
(`:61-62`、`:75`),截断处补 `\n…(truncated)`(`:41`)。
**一次性调用不该有「上下文管理」,只该有上限。**

---

## 4. R4:四个文件(222 行)

R4 成品章(`chapters/r4-execution-environments.md`)§3.3 讲了七种后端,
§3.10 讲了 computer_use。这四个文件是那两节的**接缝件**:两个桌面 GUI 专属工具,
和两个 `__init__.py`——而这两个 `__init__.py` 对同一个问题给出了**相反**的答案。

### 4.1 两个桌面 GUI 专属工具

#### `tools/read_terminal_tool.py`(93 行)—— 反向读渲染层

`tools/read_terminal_tool.py:2 @ 863e313`

```
"""Read the in-app terminal pane in the Hermes desktop GUI.

The embedded terminal's buffer lives in the desktop renderer (xterm.js), so this
tool round-trips through the gateway's blocking-prompt bridge — the same one
`clarify` uses: tui_gateway emits ``terminal.read.request``, the renderer answers
with ``terminal.read.respond``. This module is just schema + a thin dispatcher
over the platform-injected callback.
```

**场景**:用户在桌面 app 内嵌的终端里手敲了几条命令,然后问 agent「刚才那个报错什么意思」。
agent 需要读**用户屏幕上那个终端**的内容——而那份缓冲只存在于渲染进程(xterm.js)里,
内核根本没有。于是要反着走一趟:内核发请求 → 渲染进程回应。

这条链 R10B 已经从渲染侧记过(`notes/r10b-raw-message-render.md` §3.2),
**但工具这一端从来没有被引用过**。工具端的形态是「schema + 一个薄分发器」:

`tools/read_terminal_tool.py:24 @ 863e313`

```
    if callback is None:
        return tool_error("read_terminal is only available in the Hermes desktop app.")
```

`callback` 由平台在调用时注入(`registry.register(... handler=lambda args, **kw: read_terminal_tool(... callback=kw.get("callback")))`,见 `:82-92`)。
**工具模块自己不知道桥怎么走**,它只知道「有 callback 就用,没有就说这里不是桌面」。

参数处理里有一处小设计:

`tools/read_terminal_tool.py:27 @ 863e313`

```
    try:
        window = {
            key: max(floor, int(val))
            for key, val, floor in (("start", start_line, 0), ("count", count, 1))
            if val is not None
        }
```

**「不给就不放进 dict」**(`if val is not None`),而不是给一个默认值。
于是 `{}` 这个空窗口本身就是「给我可见屏幕」的信号,
渲染侧不必区分「用户没指定」和「用户指定了 0」。
两个下限(`start` 最小 0、`count` 最小 1)顺手把负数和 0 行的请求夹住。

#### `tools/close_terminal_tool.py`(70 行)—— 关掉视图,不杀进程

`tools/close_terminal_tool.py:2 @ 863e313`

```
"""Close a read-only agent terminal tab in the Hermes desktop GUI.

Each ``terminal(background=true)`` process is mirrored as a read-only tab in the
desktop's terminal pane. This tool lets the agent drop a tab it no longer needs
to show — WITHOUT killing the process (use ``process(action='kill')`` for that).
The output keeps buffering and the user can reopen the tab from the status stack.
```

**这个工具的全部价值是「区分了两个很容易被混为一谈的动作」**:
关掉一个标签页 ≠ 结束一个进程。R4 章 §3.6 讲的后台进程注册表里,
每个 `terminal(background=true)` 都在桌面上有一个只读镜像标签。
agent 起了五个后台进程,屏幕就被五个标签占满——它需要一个「收起来」的动作,
而这个动作**绝不能**变成 kill。schema 的 description 里把这句话重复了一遍
(`:41-45`),因为读 schema 的是模型,不是人。

`tools/close_terminal_tool.py:23 @ 863e313`

```
def close_terminal_tool(process_id: str) -> str:
    """Ask the desktop GUI to close a background process's read-only tab."""
    pid = (process_id or "").strip()
    if not pid:
        return tool_error("process_id is required (the background process whose tab to close).")

    return json.dumps(process_registry.request_close_terminal(pid), ensure_ascii=False)
```

**注意它不走 `read_terminal` 那条 callback 注入的路**,而是打进进程注册表的
`on_close` 汇聚点,由桌面网关把它翻成一个 `terminal.close` 事件。
两个工具同属 `toolset="terminal"`、同用 `HERMES_DESKTOP` 门控,
但**一个是请求-应答(要拿回数据),一个是单向通知(只发命令)**,
所以走了两条不同的桥。

`tools/close_terminal_tool.py:63 @ 863e313`

```
registry.register(
    name="close_terminal",
    toolset="terminal",
    schema=CLOSE_TERMINAL_SCHEMA,
    handler=lambda args, **kw: close_terminal_tool(process_id=args.get("process_id", "")),
    check_fn=check_close_terminal_requirements,
    emoji="🖥️",
)
```

`check_fn` 是**注册期就带上的可用性判据**(两个工具都是
`env_var_enabled("HERMES_DESKTOP")`),所以这两个工具在非桌面场景下
根本不会出现在给模型的工具清单里——不是调用了再报错。
**能力门控放在 schema 暴露层而不是执行层,省掉的是模型的一次错误尝试和一轮解释。**

### 4.2 两个 `__init__.py`,相反的取舍

> 注意:这两个文件都叫 `__init__.py`,而基线里有 **171 个**同名文件。
> 本节一律写全路径。

#### `tools/environments/__init__.py`(14 行)—— 只导出抽象基类

`tools/environments/__init__.py:1 @ 863e313`

```
"""Hermes execution environment backends.

Each backend provides the same interface (BaseEnvironment ABC) for running
shell commands in a specific execution context: local, Docker, SSH,
Singularity, Modal, Daytona, or Vercel Sandbox. (Modal additionally has
direct and Nous-managed modes, selected via terminal.modal_mode.)

The terminal_tool.py factory (_create_environment) selects the backend
based on the TERMINAL_ENV configuration.
"""
```

`tools/environments/__init__.py:12 @ 863e313`

```
from tools.environments.base import BaseEnvironment

__all__ = ["BaseEnvironment"]
```

**这 14 行的信息量全在「没做什么」上**:包里有 8 个后端实现
(`local` `docker` `ssh` `singularity` `modal` `managed_modal` `daytona` `vercel_sandbox`)
外加 `base` `file_sync` `modal_utils`,而 `__init__` **一个后端都不导出**。
理由很直接:`docker.py` / `modal.py` / `daytona.py` / `vercel_sandbox.py` 各自拖着
自己的 SDK,`import tools.environments` 如果把它们全拉进来,
一个只想用本地终端的用户会为七个云沙箱付启动成本。

选择权交给了工厂:

`tools/terminal_tool.py:1058 @ 863e313`

```
from tools.environments.local import LocalEnvironment as _LocalEnvironment
from tools.environments.singularity import SingularityEnvironment as _SingularityEnvironment
from tools.environments.ssh import SSHEnvironment as _SSHEnvironment
from tools.environments.docker import DockerEnvironment as _DockerEnvironment
from tools.environments.modal import ModalEnvironment as _ModalEnvironment
from tools.environments.managed_modal import ManagedModalEnvironment as _ManagedModalEnvironment
```

而两个 SaaS 后端**连在工厂里都是延迟 import 的**:

`tools/terminal_tool.py:1729 @ 863e313`

```
        from tools.environments.daytona import DaytonaEnvironment as _DaytonaEnvironment
```

`tools/terminal_tool.py:1737 @ 863e313`

```
        from tools.environments.vercel_sandbox import (
```

**三档而不是两档**:包 `__init__` 只给 ABC → 工厂模块顶部急切 import 六个 →
两个最重的在 `_create_environment` 分支里才 import。
文档里那句「七种后端 + Modal 两种模式」与目录实测一致
(8 个实现文件 = 7 种后端,`managed_modal` 是 Modal 的 Nous 托管模式),**不构成 ▲**。

#### `tools/computer_use/__init__.py`(45 行)—— 把整个公共面重新导出

`tools/computer_use/__init__.py:1 @ 863e313`

```
"""Computer use toolset — universal (any-model) macOS desktop control.

Architecture
------------
This toolset drives macOS apps through cua-driver's background computer-use
primitive (SkyLight private SPIs for focus-without-raise + pid-scoped event
posting). Unlike #4562's pyautogui backend, it does NOT steal the user's
cursor, keyboard focus, or Space — the agent and the user can co-work on the
same machine.
```

`tools/computer_use/__init__.py:37 @ 863e313`

```
# Re-export the public surface so `from tools.computer_use import ...` works.
from tools.computer_use.tool import (  # noqa: F401
    handle_computer_use,
    release_computer_use_session,
    set_approval_callback,
    check_computer_use_requirements,
    get_computer_use_schema,
    release_computer_use_session,
)
```

**同一棵 `tools/` 树下的两个包,选了相反的策略**:`environments` 只给 ABC,
`computer_use` 把 5 个公共函数全部拉到包顶层。差别的根源是**包的边界性质不同**:

- `environments` 是**多实现选一个**——调用方永远只需要其中一个,
  提前 import 全部是纯浪费。
- `computer_use` 是**一个实现的多个面**(注册、审批回调、能力检查、schema、会话释放),
  调用方需要的是「这个工具」整体。`tool.py` 无论如何都要被 import(它在里面调
  `tools.registry` 注册工具),再导出几个名字不多花钱。

**判据可以写成一句**:包是「选择」就别在 `__init__` 里替人选;包是「一件事的多个面」
就把面摆齐。

这个文件里有两处实测不成立的自述,见 §5 的 **■-B2-01**(`capture.py` 不存在)
与 **■-B2-02**(重复导出)。

---

## 5. 本片定案(▲ / ◇ / ■ / ◎)

### ▲-B2-01 —— `hermes memory` / Honcho「Full Config Reference」不全

**文档侧**(判定整段 + 确认归哪个标题管):`website/docs/user-guide/features/honcho.md`
的 `## Configuration Options` 下有 `### Full Config Reference` 一节,
其下是一张 18 行的 `| Key | Default | Description |` 表。
标题用词 **Full**,而表内实际只覆盖 18 个键。

**代码侧**:`plugins/memory/honcho/config_schema.py` 声明了 28 个键,
其中 **12 个**在这张「Full」表里没有;反过来,表里有 **2 个**(`contextCadence`
`dialecticCadence`)不在 schema 里——它们在代码里是真键
(`plugins/memory/honcho/client.py:689`:`host_block.get("contextCadence"),`),
只是桌面面板不暴露。

```verify
cd /home/user/hermes-agent && python3 - <<'PY'
import re, pathlib
doc = pathlib.Path("website/docs/user-guide/features/honcho.md").read_text()
sec = doc.split("### Full Config Reference")[1].split("**Session strategy**")[0]
dk = re.findall(r"^\| `([A-Za-z]+)` \|", sec, re.M)
sch = re.findall(r'key="([A-Za-z]+)"', pathlib.Path("plugins/memory/honcho/config_schema.py").read_text())
print("doc keys    :", len(dk))
print("schema keys :", len(sch))
print("doc-only    :", sorted(set(dk) - set(sch)))
print("schema-only :", sorted(set(sch) - set(dk)))
PY
```

```text
doc keys    : 18
schema keys : 28
doc-only    : ['contextCadence', 'dialecticCadence']
schema-only : ['aiPeer', 'apiKey', 'baseUrl', 'environment', 'initOnSessionStart', 'peerName', 'reasoningHeuristic', 'reasoningLevelCap', 'sessionPeerPrefix', 'sessions', 'timeout', 'workspace']
```

**为什么判 ▲ 而不是 ◎**:◎ 的定义是「文档成立但显著保守」。
这里文档不是保守——「Full」是一个**全称断言**,而它不成立。
表里每一行的内容都对;错的是标题声称的覆盖面。
*两个方向的差集都要报*:文档漏了 12 个,schema 漏了 2 个,
**两份名单没有任何一方是另一方的超集**,即不存在「以谁为准」的简单答案。

### ▲-B2-02 —— `subcommands` 包自述「each subcommand group」已拆完,实测 16 个未拆

**文档侧**:`hermes_cli/subcommands/__init__.py:5-8` 的
`This package breaks that tree apart: each subcommand group owns a
``build_<group>_parser(subparsers, ...)`` function in its own module, and
``main()`` calls those builders instead of inlining the argument definitions.`

**代码侧**:`main()` 里仍有 16 个顶层组内联(§1.6 的 verify 块)。

**整段判定(按 CLAUDE.md 要求)**:这一段的最后一句是
`hermes_cli/subcommands/__init__.py:15`:`Part of the god-file decomposition plan (Phase 2).`
——它自称是一个**阶段**。把整段合起来读,"each subcommand group owns…" 是在描述
**这个包的组织方式**(凡进了这个包的组都按这个形状),不是在断言「全部组都进来了」。
**因此本条按「弱 ▲」记:字面读为全称即不成立,按整段读则勉强成立。**
留给主线定夺是否计入跨轮 ▲ 计数;本片倾向**不计入**,理由是
CLAUDE.md 的 ◎ 条特意说过「字面为真就不是 ▲」,而这条的争点正是字面 vs 段落。
*但它作为学习结论仍要写下来*:**读一份「Phase N」的自述时,
「已经做到什么程度」必须去数,不能从描述里读。**

### ■-B2-01 —— `tools/computer_use/__init__.py` 的接线图指向一个不存在的文件

`tools/computer_use/__init__.py:20 @ 863e313`

```
* `tool.py`       — registers the `computer_use` tool via tools.registry.
* `backend.py`    — abstract `ComputerUseBackend`; swappable implementation.
* `cua_backend.py`— default backend; speaks MCP over stdio to `cua-driver`.
* `schema.py`     — shared schema + docstring for the generic `computer_use`
                    tool. Model-agnostic.
* `capture.py`    — screenshot post-processing (PNG coercion, sizing, SOM
                    overlay if the backend did not).
```

`capture.py` **在整个基线仓库里都不存在**;同时包里真实存在的
`browser_route.py` / `doctor.py` / `permissions.py` / `vision_routing.py` 四个模块
一个都没被列。

```verify
cd /home/user/hermes-agent && echo "capture.py 在全仓的命中数: $(find . -name capture.py -not -path './node_modules/*' | wc -l)" && ls tools/computer_use/*.py | sed 's#.*/##'
```

```text
capture.py 在全仓的命中数: 0
__init__.py
backend.py
browser_route.py
cua_backend.py
doctor.py
permissions.py
schema.py
tool.py
vision_routing.py
```

**搜索面**:`find . -name capture.py`,基线仓库根起全树递归,
仅排除 `./node_modules/*`(第三方安装物)。命中 0。

它描述的功能确实存在,只是没有独立成文件:PNG/JPEG 尺寸嗅探在
`tools/computer_use/tool.py:860` 与 `tools/computer_use/cua_backend.py:946` **各写了一份**,
缩放/重编码在 `tools/computer_use/tool.py:1085`:`img = Image.open(BytesIO(raw))`。
**所以这不是「文件被删了忘改文档」,更像「计划中的拆分从未发生,而接线图先写好了」**
——同一段代码在两个文件里各存一份,正是缺了那个共用模块的症状。

### ■-B2-02 —— 同一个名字在 import 元组里出现两次

`tools/computer_use/__init__.py:38 @ 863e313`

```
from tools.computer_use.tool import (  # noqa: F401
    handle_computer_use,
    release_computer_use_session,
    set_approval_callback,
    check_computer_use_requirements,
    get_computer_use_schema,
    release_computer_use_session,
)
```

`release_computer_use_session` 在 `:40` 和 `:44` 各出现一次。
Python 允许,行为无差别(第二次覆盖第一次,同一对象)。
**记它的理由不是它有害,而是它说明了这一处没有 linter 覆盖**——
行首那个 `# noqa: F401`(压掉「导入未使用」)恰恰暗示这里跑过 flake8,
而 F811(重复定义)没被报,或被同一条 `noqa` 连带压掉了。
一个「为了消警告而加的 noqa」把另一个真警告一起消掉了,是很典型的形态。

### ■-B2-03 —— `hermes memory --help` 的 provider 名单漏了一个真 provider

`hermes_cli/subcommands/memory.py:17 @ 863e313`

```
        description=(
            "Set up and manage external memory provider plugins.\n\n"
            "Available providers: honcho, openviking, mem0, hindsight,\n"
            "holographic, retaindb, byterover.\n\n"
```

7 个。而真正的 provider 发现是**目录扫描**,实测 8 个:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c "
import sys; sys.path.insert(0, '/home/user/hermes-agent')
from plugins.memory import discover_memory_providers
print('discover_memory_providers():', sorted(x[0] for x in discover_memory_providers()))" && printf 'memory.py 帮助文本硬编码名单:\n' && sed -n '19,20p' hermes_cli/subcommands/memory.py
```

```text
discover_memory_providers(): ['byterover', 'hindsight', 'holographic', 'honcho', 'mem0', 'openviking', 'retaindb', 'supermemory']
memory.py 帮助文本硬编码名单:
            "Available providers: honcho, openviking, mem0, hindsight,\n"
            "holographic, retaindb, byterover.\n\n"
```

漏的是 **`supermemory`**,它是个真 provider:`plugins/memory/supermemory/__init__.py:578`
有 `get_config_schema`,`agent/skill_commands.py:36` 也把它列进记忆 provider。
`hermes memory setup` 会把它列出来(发现是动态的),但 `hermes memory --help` 不会。

**这正是 r8b 章 §4.3「两份必须手工对齐的名单」的第三副面孔**:
一份是动态计算的真名单,一份是写在 help 字符串里的手抄本,
**没有任何机制在两者分叉时报警**。

### ■-B2-04 —— 三条写进代码的 `路径:行号` 交叉引用全部已漂

R2 这两个模块用 docstring 给读者指路,指的都是**别的文件的具体行号**。三条全错:

```verify
cd /home/user/hermes-agent && for r in agent/chat_completion_helpers.py:2544 run_agent.py:1140 agent/conversation_loop.py:3464; do f=${r%:*}; n=${r#*:}; printf '%-40s |%s\n' "$r" "$(sed -n "${n}p" "$f")"; done
```

```text
agent/chat_completion_helpers.py:2544    |    if agent._interrupt_requested:
run_agent.py:1140                        |        A provider/model switch is a durable state change operators must see,
agent/conversation_loop.py:3464          |                # genuinely successful content is detected later (~L4127).
```

前两条写在同一个 docstring 段落里(**含 RST 双反引号,故用围栏块引,不用表格**):

`agent/reasoning_timeouts.py:7 @ 863e313`

```
* Stream stale detector:   ``HERMES_STREAM_STALE_TIMEOUT``     default 180s
                           ``agent/chat_completion_helpers.py:2544``
* Non-stream stale detector: ``HERMES_API_CALL_STALE_TIMEOUT``  default 90s
                           ``run_agent.py:1140``
```

第三条见 §3.2 已引的 `agent/thinking_timeout_guidance.py:19` 那一段
(`` ``agent/conversation_loop.py:3464-3486`` fires for large-file-write ``)。

三处的**真实位置**:

`agent/chat_completion_helpers.py:362 @ 863e313`

```
        _base = env_float("HERMES_STREAM_STALE_TIMEOUT", 180.0)
```

`run_agent.py:1409 @ 863e313`

```
        env_timeout = os.getenv("HERMES_API_CALL_STALE_TIMEOUT")
```

`agent/conversation_loop.py:5386 @ 863e313`

```
                    _is_stream_drop = (
```

三条都不是「差一两行」,而是**差一两千行**——`_is_stream_drop` 从 3464 漂到 5386。

**这条为什么值得单列**:hermes-study 这个项目自己造了 `verify_citations.py`,
理由就是「人写的 `路径:行号` 会漂,而没有机制会发现」。
**基线仓库给出了同一条规律的独立证据**:一个 4 万人月级别的代码库,
在**自己的代码注释里**写下的行号引用,三取三漂。
这不是 hermes 作者的疏忽,是这种引用形式的固有性质——
**除非有东西去跑它,`路径:行号` 就一定会漂。**

### ■-B2-05 —— Honcho 配置面板的占位符与实际默认值不符

`plugins/memory/honcho/config_schema.py:216 @ 863e313`

```
        ProviderField(
            key="dialecticMaxChars",
            label="Max result chars",
            kind=KIND_NUMBER,
            description="Max chars of dialectic result injected into the system prompt.",
            placeholder="1200",
            group="Dialectic",
        ),
```

`plugins/memory/honcho/client.py:403 @ 863e313`

```
    # Automatic-injection cap; explicit honcho_reasoning calls bypass it.
    dialectic_max_chars: int = 600
```

```verify
cd /home/user/hermes-agent && sed -n '221p' plugins/memory/honcho/config_schema.py && sed -n '404p' plugins/memory/honcho/client.py
```

```text
            placeholder="1200",
    dialectic_max_chars: int = 600
```

**为什么这是缺陷而不是「占位符本来就不是默认值」**:同一个文件里另外四个数字型
placeholder **全部等于实际默认值**——`timeout` 的 `"30"` 对
`plugins/memory/honcho/client.py:244`:`_DEFAULT_HTTP_TIMEOUT = 30.0`,
`messageMaxChars` 的 `"25000"`、`dialecticMaxInputChars` 的 `"10000"`、
`dialecticDepth` 的 `"1"` 都与文档表和代码一致。
**在一份「占位符=默认值」的惯例里,唯一的例外就是错**,
用户把框留空得到的是 600,面板却提示 1200。
(文档表 `website/docs/user-guide/features/honcho.md:120` 那一行写的也是 `600`,
所以是 schema 这一处孤立地不对。)

### ◇-B2-01 —— Honcho 的浏览器/设备码登录,面向用户的文档一字未提

`website/docs/user-guide/features/honcho.md` 的 `## Setup` 一节只教
「把 `HONCHO_API_KEY` 写进 `~/.hermes/.env`」;
`### Self-Hosted Honcho with Authentication` 讲的是自托管 JWT。
**整份文档没有 OAuth / 浏览器登录 / 设备码的任何字样**,
而代码里 `hermes honcho setup` 的默认选项就是 `oauth`
(`plugins/memory/honcho/cli.py:646`:`        default_method = "oauth"`)。

**搜索面**:`grep -rn -i` 模式 `HONCHO_OAUTH|honcho.*oauth|oauth.*honcho`,
范围 `website/` 全树的 `*.md` + `*.mdx`,加 `README.md`、`AGENTS.md`;命中 0。
未覆盖的形态是「用别的词说这件事」(如只写 "sign in with your browser" 而不含 oauth)
——本片人工通读了 `website/docs/user-guide/features/honcho.md` 全部 265 行,
`Setup` 与 `CLI Commands` 两节均无此类描述。

### ◎-B2-01 —— Honcho 声明的 28 个配置键,插件侧全部有对应读取点

反向检查:schema 里声明的每个键,在 `plugins/memory/honcho/` 下(排除 schema 文件本身)
都至少出现一次同名字符串字面量,**没有「面板里能设、代码里没人读」的死旋钮**。

**口径要如实说**:这是字符串字面量匹配,`timeout` / `sessions` / `environment`
这类通用词的命中数里必然掺有噪音;这条检查能证否「某个键完全没人读」,
**不能**证明「每个键都被正确地读了」。真正的对齐(键名拼写 × 读取路径)
是 r6 章 §5 那条系统性风险,超出本片范围。

---

## 6. 测试作行为规格

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh tests/agent/test_reasoning_stale_timeout_floor.py tests/agent/test_thinking_timeout_guidance.py tests/agent/test_oneshot.py tests/honcho_plugin/test_oauth_flow.py tests/hermes_cli/test_subcommands_batch.py tests/hermes_cli/test_subcommands_followup.py 2>&1 | grep -o '=== Summary:.*(100% complete)'
```

```text
=== Summary: 6 files, 85 tests passed, 0 failed (100% complete)
```

**85 passed / 0 failed / 0 skipped**,venv 87 包(见 §0)。
*注:`grep -o ... '(100% complete)'` 是刻意截断的——Summary 行尾还有耗时与并发段
(实测形如 `in 2.3s (8 workers) ===`),那两个数**每次重跑都不同**,
整行贴进 `text` 块会让这条证据必然失配。**「shell 命令即证据」要求的是可复现,
所以命令本身就得把不可复现的部分切掉**,而不是把它抄进块里再解释。*

几处值得当规格读的:

| 用例 | 钉住的行为 |
|---|---|
| `tests/hermes_cli/test_subcommands_batch.py:51`:`SINGLE_HANDLER_CASES = [` | 23 个「单处理函数」壳的参数化表:每个壳建一棵树、解析一次样例 argv、断言 `ns.func is handler` ——**把「注入的处理函数确实落到了 `Namespace.func`」当作这一层的核心契约** |
| `tests/hermes_cli/test_subcommands_batch.py:68`:`    ("import", build_import_cmd_parser, "cmd_import", ["import", "/tmp/x.zip"]),` | 唯一带位置参数的样例——`import` 必须给 zipfile,证明壳里那个 `add_argument("zipfile")` 是必填 |
| `tests/honcho_plugin/test_oauth_flow.py:443`:`    st = oauth_flow.start_loopback_flow_background(config_path=Path("/t/honcho.json"), host="hermes")` | 后台流的完整往返(启动 → 轮询 status 到 `connected`),即 §2.2(9) 那段幂等/作用域逻辑的行为规格 |
| `tests/honcho_plugin/test_oauth_flow.py:482`:`    assert hasattr(mod, "start_loopback_flow_background") and hasattr(mod, "get_flow_status")` | **把 §2.2 那条鸭子类型契约本身写成了断言**——路由层按约定分发,于是「这两个函数必须存在」成为可测的接口约束 |

---

## 7. 需要但没装 / 被拦

无。本片全部工作在既有 venv(87 包)与基线只读副本内完成,未装任何包、未触网。
基线收工检查:`git -C /home/user/hermes-agent status --porcelain` 为空(见 §8 前的自校验)。

---

## 8. 移交

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议去向 |
|---|---|---|---|
| **H-R11B-B2-a** | `tools/computer_use/__init__.py:26`:`overlay if the backend did not).` | 包的接线图列了一个全仓不存在的 `capture.py`(该行是它的续行),而它描述的 PNG 尺寸嗅探实际在 `tools/computer_use/tool.py:860`:`"""Return (width, height) for common inline screenshot formats.` 与 `tools/computer_use/cua_backend.py:946` **各写了一份**;需确认这是「计划中的拆分未发生」还是「拆完又被合回」 | 主线定案 ■-B2-01 时一并判;若入成品章,与 R4 章 §3.10 合并叙述 |
| **H-R11B-B2-b** | `hermes_cli/subcommands/memory.py:19`:`"Available providers: honcho, openviking, mem0, hindsight,\n"` | help 文本硬编码 7 个 provider,目录扫描实测 8 个(漏 `supermemory`);本片只查了这一处手抄名单,**未做全仓「provider 名单手抄本」普查**——`hermes_cli/config_defaults.py:1660`:`# "hindsight", "holographic", "retaindb", "byterover".` 的注释里还有一份同款 7 项名单 | 下一轮做一次 provider/toolset 名单手抄点普查,与 r8b 章 §4.3 的两份名单合并成一条跨轮结论 |
| **H-R11B-B2-c** | `agent/reasoning_timeouts.py:62`:`_REASONING_STALE_TIMEOUT_FLOORS: tuple[tuple[str, int], ...] = (` | 这张 30 行静态表是「断连是否会触发压缩删历史」的唯一守门人(`agent/error_classifier.py:956`:`if get_reasoning_stale_timeout_floor(model) is not None:`),但**没有任何机制保证新推理模型上架时有人来加行**;需确认是否有 CI/脚本对着 models.dev 目录做覆盖检查 | 下一轮查 `models.dev` 目录同步链路(R8B 已知本容器该目录条目数为 0,需在有网环境判) |
| **H-R11B-B2-d** | `plugins/memory/honcho/oauth_flow.py:365`:`    if returned_state != state:` | CSRF state 用 `!=` 直接比,非常量时间;MCP 侧(r6 章 §3.8)记的是「SDK 生成并常量时间比对」。本片判**不构成可利用面**(state 是 `secrets.token_urlsafe(32)`、失败即抛、无重试预言机),但两套 OAuth 客户端在同一仓库里对同一问题给出了不同强度的答案 | 仅记录,不建议改;若 R12 装订时讲「两套 OAuth 的取舍」,此处是最锋利的对照点 |
| **H-R11B-B2-e** | `hermes_cli/subcommands/__init__.py:5`:`into one 3,300-line function. This package breaks that tree apart: each` | 拆分只做了一半:42 个 builder 模块 vs `main()` 里仍内联的 16 个顶层组;本片按「弱 ▲」记(▲-B2-02),**是否计入跨轮 ▲ 计数交主线** | 主线定案 |
