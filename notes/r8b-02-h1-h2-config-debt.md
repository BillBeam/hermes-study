# r8b-02 · 结算 R8A 移交的 H-1 / H-2

> 溯源约定:凡断言紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 实跑环境:`/home/user/hermes-venv`(`pip list` 89 个包 = `[dev]` extra + `aiohttp 3.14.1` + `brotlicffi 1.2.0.1`)。

## 0. 两笔账的原文

R8A 报告 §11 把两笔账明确留给本轮:

- **H-1** —— 锚点 `cli.py:441`(`load_cli_config` 的内联 `defaults`):
  "89 键中 28 个不在 `DEFAULT_CONFIG`……**未做的是逐个确证这 15 个是否真被读**
  —— 已证 2 个真被读且收到假警告,其余待查"。
- **H-2** —— 锚点 `cli.py:599`(`defaults[key].update(...)`):
  "浅合并的**实际影响面**未穷举:哪些从 `CLI_CONFIG` 读的嵌套键**没有**硬编码兜底,
  那些才是会真出事的"。

本节结论先行:

- **H-1 复算通过**,并从中挖出一条 R8A 没走到的后果:
  **`agent.personalities` 这个键只存在于 `cli.py` 那份默认值里,于是四个面里有两个面看不见 14 个内置人格。**
- **H-2 影响面已穷举完毕,而且很小**:受害叶子**恰好 24 个**,其中 **10 个被读取点兜底救回、14 个没有**。
  没被救回的那 14 个,正是 `agent.personalities` 的 14 个内置人格。
  **两笔账在同一个键上合流了。**

---

## 1. H-1:复算与名单

用 AST 展开 `cli.py` 的 `defaults` 与 `config_defaults.py` 的 `DEFAULT_CONFIG` 求差
(脚本 `scripts/r8b_cli_defaults.py`,遍历方式沿用 R8A `scripts/config_table.py`
——逐节点走而不 `literal_eval` 整棵树,因为 `DEFAULT_CONFIG` 含非字面量值)。

实跑输出原样抄录:

```
# H-1  cli.py:441 `defaults`  vs  config_defaults.py:7 DEFAULT_CONFIG
cli.py defaults 展开键数 : 89
DEFAULT_CONFIG 展开键数  : 856
CLI 专属键(H-1)        : 28
```

**与 R8A 报的 89 / 28 逐位相同**,独立复算通过。28 条按 R8A 的分法确认:

| 类别 | 条数 | 键 |
|---|---|---|
| 人格相关 | 15 | `agent.personalities` + 其 14 个叶子 |
| 真开关 | 13 | `agent.verbose` / `agent.system_prompt` / `agent.prefill_messages_file` / `agent.reasoning_effort` / `clarify` / `clarify.timeout` / `code_execution.timeout` / `code_execution.max_tool_calls` / `model.default` / `model.base_url` / `model.provider` / `terminal.env_type` / `terminal.lifetime_seconds` |

### 1.1 H-1 的后果:同一个键名,四个面读出两种结果

R8A 已证 `agent.reasoning_effort` 与 `agent.system_prompt` "真被读且收到假警告"。
本轮追的是**剩下那 15 个人格键**,结果比"是否被读"更有意思。

`cli.py` 的默认值里,人格挂在 **`agent.personalities`** 下,带 14 个内置人格:

`cli.py:481 @ 863e313`

```python
            "personalities": {
                "helpful": "You are a helpful, friendly AI assistant.",
```

而 `DEFAULT_CONFIG` 里根本没有 `agent.personalities`——它有的是一个**顶层** `personalities`,
值为空字典:

`hermes_cli/config_defaults.py:2126 @ 863e313`

```python
    # Custom personalities — add your own entries here
    # Supports string format: {"name": "system prompt"}
    # Or dict format: {"name": {"description": "...", "system_prompt": "...", "tone": "...", "style": "..."}}
    "personalities": {},
```

**两个装载器把同一个概念放在了不同层级**:CLI 面 `agent.personalities`(有 14 个内置),
主装载器顶层 `personalities`(空)。而**全部读取点读的都是 `agent.personalities`**:

`cli.py:4490 @ 863e313`

```python
        self.personalities = CLI_CONFIG["agent"].get("personalities", {})
```

`gateway/slash_commands.py:2502 @ 863e313`

```python
            personalities = cfg_get(config, "agent", "personalities", default={})
```

于是**顶层 `personalities` 没有任何读取点**——它是一个死键,而它的注释
("add your own entries here")**恰好把用户往错的层级引**:照着写 `personalities:` 顶层段的用户,
`/personality` 永远看不到自己新增的人格。
校验器那侧还专门给这个错层级开了绿灯:

`hermes_cli/config.py:4660 @ 863e313`

```python
    "personalities",
```

(该常量是 `_OPEN_DICT_TOP_LEVEL_KEYS`,`hermes_cli/config.py:4654 @ 863e313`,
语义是"这些顶层键之下接受任意用户自定义子键,schema 不深查"。
**于是用户写错层级不会收到任何警告。**)

### 1.2 四个面实跑对照(stock 安装,无 config.yaml)

```
1) CLI 面      cli.py:4490                  -> 14 个
2) 主装载器    load_config()                -> 0 个
3) 消息网关面  _load_gateway_config()       -> 0 个
4) TUI 网关面  server.py:5811               -> 14 个
```

**同一个 `/personality` 命令,CLI 与 TUI 列出 14 个内置人格,消息网关(Slack/Discord 等)
列出 0 个**——用户在手机上对着同一个 Hermes 打 `/personality kawaii`,得到的是
"No personalities configured"。

第 3 面之所以是 0,是因为消息网关读的是**原始读**、完全不带默认值:

`gateway/run.py:3145 @ 863e313`

```python
def _load_gateway_config() -> dict:
    """Load and parse ~/.hermes/config.yaml, returning {} on any error.
```

第 4 面之所以是 14,是因为 TUI 网关**专门绕开主装载器去调 CLI 装载器**:

`tui_gateway/server.py:5815 @ 863e313`

```python
        return (load_cli_config().get("agent") or {}).get("personalities", {}) or {}
```

### 1.3 仓库自己知道这件事,而且只修了一半

补全器那一处留下了完整的病历:

`hermes_cli/commands.py:2022 @ 863e313`

```python
            # Resolve from the same source the runtime applies personalities —
            # agent.personalities via the CLI config (which ships the built-ins).
            # load_config()'s schema has no agent.personalities, so the completer
            # used to come back empty even with personalities available.
            from cli import load_cli_config

            personalities = (load_cli_config().get("agent") or {}).get("personalities", {}) or {}
```

**注释把病根说得一字不差**("`load_config()` 的 schema 里没有 `agent.personalities`"),
修法是让这一处改调 `load_cli_config()`。TUI 网关那处(1.2 的第 4 面)用的是同一招。
**但消息网关那处没跟上**,至今仍走 `_load_gateway_config()`。

TUI 网关甚至还写了一条**诊断**去提示这个失败形态:

`tui_gateway/server.py:4939 @ 863e313`

```python
            and agent_cfg.get("personalities") is None
```

`tui_gateway/server.py:4942 @ 863e313`

```python
                "`display.personality` is set but `agent.personalities` is empty/null; "
```

**结论 ■-R8B-01(高置信,已实跑复现)**:`agent.personalities` 是 CLI 专属键(H-1 名单第一条),
四个消费面里两个能看见内置人格、两个看不见;仓库已在两处打了"改调 CLI 装载器"的补丁并留下注释,
**消息网关面漏掉了**。这条是 R8A"两份默认值"头条的**第三种后果形态**:
前两种是"值不同"(clarify 780 秒)与"假警告",这一种是**键的层级不同**,
于是同一条斜杠命令在不同入口给出不同的世界。

---

## 2. H-2:浅合并的影响面,穷举完毕

### 2.1 判据:只有深度 >= 3 的键会连坐

合并代码是**对顶层键**做一层 `update`:

`cli.py:598 @ 863e313`

```python
                    if isinstance(defaults[key], dict) and isinstance(file_config[key], dict):
                        defaults[key].update(file_config[key])
```

`dict.update` 只替换**第一层**子键。因此:

- **深度 2**(`top.leaf`)**安全**:用户写 `agent.verbose`,`update` 只替换 `verbose` 这一个子键,
  `agent` 下其余默认值原样保留。
- **深度 3+**(`top.sub.leaf`)**连坐**:用户写 `browser.camofox.rewrite_loopback_urls`,
  `update` 把 `defaults["browser"]["camofox"]` **整个换成**用户那一个叶子的字典,
  **同级兄弟叶子全部消失**。

所以受害集合 = `cli.py` 默认值里**本身是字典、且叶子数 >= 2 的二级子树**。
(叶子数为 1 的子树整体替换也丢不了别的东西,故排除。)

### 2.2 穷举结果:恰好 4 棵子树 / 24 个叶子

`scripts/r8b_cli_defaults.py` 实跑输出:

```
### agent.personalities   cli.py:481   (14 个叶子)
### auxiliary.vision      cli.py:530   (4 个叶子)
### auxiliary.web_extract cli.py:536   (4 个叶子)
### browser.camofox       cli.py:464   (2 个叶子)

受害子树 4 个,涉及叶子 24 个
```

**这就是 H-2 要的那个"实际影响面",它是完整的**:`cli.py` 的默认值一共只有这 4 棵三层子树。

### 2.3 逐棵判定:谁被读取点兜底救回来了

**(a) `browser.camofox`(2 叶) —— 救回来了。**
两个叶子的读取点各自自带兜底,**且兜底值与默认值字面量相同**:

`tools/browser_camofox.py:245 @ 863e313`

```python
    return bool(camofox_cfg.get("rewrite_loopback_urls"))
```

(`.get()` 无默认 → `None` → `bool(None)` = `False`,与 `cli.py:465` 的默认值 `False` 一致)

`tools/browser_camofox.py:250 @ 863e313`

```python
    return (
        os.getenv("CAMOFOX_LOOPBACK_HOST_ALIAS", "").strip()
        or str(camofox_cfg.get("loopback_host_alias") or "").strip()
        or "host.docker.internal"
    )
```

(末尾 `or "host.docker.internal"` 与 `cli.py:466` 的默认值一致)

实跑确认"确实丢了、但取值不变":

```
browser.camofox  合并后 = {'rewrite_loopback_urls': True}  (loopback_host_alias 是否还在: False )
读取点兜底后的实际取值 _loopback_rewrite_host(c) = 'host.docker.internal'
```

**这正是 R8A 说的"受害键的默认值字面量在仓库里存在三份,读取点自带硬编码兜底"——本轮把它验完了。**

**(b) `auxiliary.vision` / `auxiliary.web_extract`(各 4 叶) —— 救回来了。**
这 8 个叶子在 `cli.py` 内部的唯一消费点是环境变量桥,四个读取点**全部带 `""` 兜底**:

`cli.py:759 @ 863e313`

```python
        prov = str(task_cfg.get("provider", "")).strip()
        model = str(task_cfg.get("model", "")).strip()
        base_url = str(task_cfg.get("base_url", "")).strip()
        api_key = str(task_cfg.get("api_key", "")).strip()
```

丢掉的唯一非空默认值是 `provider: "auto"`,而桥接判据把 `"auto"` 与 `""` **归为同一路**:

`cli.py:763 @ 863e313`

```python
        if prov and prov != "auto":
```

`"auto"` 与 `""` 都不会写环境变量,**行为完全相同**。实跑确认丢失发生但无后果:

```
auxiliary.vision 合并后 = {'model': 'some-vision-model'}  (默认 provider=auto 是否还在: False )
```

(真正消费 `auxiliary.*` 的 `agent/auxiliary_client.py` 走主装载器,
`DEFAULT_CONFIG` 自带同名子树,不受 `cli.py` 这份浅合并影响。)

**(c) `agent.personalities`(14 叶) —— 没救回来,这就是 H-2 的答案。**

读取点的兜底是 `{}`(`cli.py:4490`,原文见 §1.1),
**空字典兜不回 14 个内置人格**。实跑复现:

用户配置只写了一个自定义人格:

```yaml
agent:
  personalities:
    grumpy: "You are a grumpy assistant."
```

```
agent.personalities 键数 = 1
键名 = ['grumpy']
内置 kawaii 还在吗 : False
内置 catgirl 还在吗: False
```

对照组(无 `config.yaml`):

```
agent.personalities 键数 = 14
键名 = ['catgirl', 'concise', 'creative', 'helpful', 'hype', 'kawaii', 'noir', 'philosopher', 'pirate', 'shakespeare', 'surfer', 'teacher', 'technical', 'uwu']
```

用户可见症状在 `/personality` 的列表里:

`hermes_cli/cli_commands_mixin.py:1356 @ 863e313`

```python
                print(f"  Available: none, {', '.join(self.personalities.keys())}")
```

**加一个自己的人格 = 删掉全部 14 个内置人格**,而用户做的事是配置系统里最自然的一件事
——"我想加一个我自己的"。

### 2.4 H-2 定案

| 受害子树 | 叶子 | 读取点兜底 | 是否真出事 |
|---|---|---|---|
| `browser.camofox` | 2 | 有,且与默认值相同 | 否 |
| `auxiliary.vision` | 4 | 有(`""`),且与桥接判据等价 | 否 |
| `auxiliary.web_extract` | 4 | 同上 | 否 |
| **`agent.personalities`** | **14** | **有,但是 `{}`,兜不回内容** | **是,已实跑复现** |

**24 个受害叶子里 10 个安全、14 个出事,而出事的那 14 个是同一棵子树。**

**这条比"两份默认值很危险"更精确,也更可迁移**:
浅合并的危害**不取决于合并本身**,取决于**读取点的兜底值能不能重建被删掉的内容**。
`camofox` 的兜底是一个**标量**,与默认值字面量相同,所以能重建;
`personalities` 的兜底是一个**空容器**,而丢掉的是**容器里的 14 条内容**——
**标量兜得回,容器兜不回。**

> **给自己造 harness 的一条**:凡"用户可增补的字典"(人格、别名、快捷命令、模型目录……),
> 内置条目**不能只放在默认值字典里**靠合并存活。要么合并时对这类子树做深合并,
> 要么把内置条目放在**读取点**而不是默认值里(`{**BUILTIN, **user}`)。
> 判据很简单:**默认值是"内容"而不是"取值"时,浅合并一定会丢内容。**

---

## 3. 附带更正 R8A 的一处措辞

R8A 头条写"`browser.camofox` 一边 **6 个键**、另一边 **1 个键**"。
本轮实测 `cli.py` 的 `browser.camofox` 只有 **2 个**叶子
(`rewrite_loopback_urls` / `loopback_host_alias`,`cli.py:464-467 @ 863e313`);
6 这个数来自**主装载器** `DEFAULT_CONFIG` 那一侧的 `browser.camofox`。
R8A 的对照本身成立(两侧键数不同),**但"一边 6 个"说的是主装载器侧、不是 `cli.py` 侧**,
原文容易被读成两侧都在 `cli.py` 的默认值里。此处仅为措辞澄清,不影响 R8A 结论。

## 4. 移交

- **H-2 已结清**,无残留。
- **■-R8B-01(§1.3)** 的修法有两种(改调 `load_cli_config()`,或把内置人格移进
  `DEFAULT_CONFIG` 的 `agent.personalities`),**本仓库只记录不修**。
- 顶层死键 `personalities`(`hermes_cli/config_defaults.py:2129`)与
  `_OPEN_DICT_TOP_LEVEL_KEYS` 里的同名条目(`hermes_cli/config.py:4660`)是否该删,
  属配置面(R8A)的收尾判断,**不在本轮范围**,记为 **H-R8B-a** 移交 R11 复盘。
