# r8d-str · `hermes egress` —— 出站代理子命令(主线补漏)

> **本卷的由来是一次分区失误,如实记在这里。** R8D 把 125 个 L2 文件分给三个测绘位时,
> 主线写分区清单时漏掉了 `hermes_cli/proxy_cli.py`(903 行)——三份清单加起来是 124 个,
> 而台账是 125 个。收尾时用"逐个 L2 文件的 basename 是否出现在 `notes/r8d-str-*.md` 里"
> 机械核对才发现。**由主线补做,不留黑洞。**
> 溯源约定同全项目:锚点 `路径:行号 @ 863e313` 单独成行、置于块前。

---

## 1. 它是什么:与 `hermes proxy` **方向相反**的另一个代理

这是本卷最该先讲的一件事,因为它是个**命名陷阱**。仓库里有两个"proxy":

| 命令 | 方向 | 实现位置 | 谁读过 |
|---|---|---|---|
| `hermes proxy` | **入站**:把 OAuth 上游包装成 OpenAI 兼容接口,供本机客户端调用 | `hermes_cli/proxy/**` | R8D 簇 E(L1 精读) |
| `hermes egress` | **出站**:管理一个 `iron-proxy` 二进制,约束 agent 自己往外发的流量 | `hermes_cli/proxy_cli.py`(本卷) | 本卷(L2) |

而 `proxy_cli.py` 这个**文件名**属于后者——它不在 `proxy/` 包里,却叫 `proxy_cli`。
作者自己也意识到了这个坑,在模块 docstring 末尾专门写了一段消歧:

`hermes_cli/proxy_cli.py:12-15 @ 863e313`

```python
The top-level command is ``hermes egress``.  Note that the inbound OAuth
reverse-proxy command (``hermes proxy``) lives elsewhere in
``hermes_cli/main.py`` — different direction, different purpose.
```

**◇-1**:这段消歧只存在于源码 docstring。对一个按文件名找代码的读者,
`proxy_cli.py` 与 `proxy/` 包看起来是同一个东西的两半,实际是两个方向相反的子系统。

---

## 2. 结构:8 个子命令 + 一个向导

`hermes_cli/proxy_cli.py:1-9 @ 863e313`

```python
"""CLI handlers for ``hermes egress ...``.

Subcommands:
    install  — download the pinned iron-proxy binary
    setup    — interactive wizard: install binary, generate CA, mint tokens, write config
    start    — launch the proxy as a managed subprocess
    stop     — terminate the managed proxy
    status   — show binary version + config presence + listen state + mappings
    disable  — flip ``proxy.enabled`` to False (does not stop a running proxy)
    config   — print the generated proxy.yaml path (for debugging / external review)
```

行数分布很集中:`cmd_setup`(`:152`–`:545`,约 394 行)一个函数占了全文件的 44%——
它是那个"装二进制 → 生成 CA 证书 → 铸令牌 → 写配置"的交互向导。
其余 7 个子命令合计不到 300 行,基本是薄包装,真逻辑在
`agent/proxy_sources/iron_proxy`(2,494 行,属 UNCLAIMED 桶,**本轮未读**)。

**这也是本卷能给出的最有用的一句导航**:想弄懂 egress 代理**做什么**,
读 `proxy_cli.py` 没用,它只管命令面;要读 `agent/proxy_sources/iron_proxy.py`。

---

## 3. 两处值得记的实现判断

### 3.1 `disable` 故意不停进程,并且明说

docstring 里那句 "does not stop a running proxy"(见 §2)不是遗漏,是刻意的,
代码里还专门给了提示:

`hermes_cli/proxy_cli.py:833-840 @ 863e313`

```python
    # Use the public get_status() pid (which already incorporates the
    # _pid_alive check) instead of reaching into ip._read_pid().  That
    # private accessor only proves the pidfile is non-empty — a stale
    # pidfile from a crashed previous run would fire the warning
    # spuriously.
    if ip.get_status().pid is not None:
        console.print(
            "  iron-proxy is still running — stop it with "
```

**配置开关与进程生命周期解耦**:`disable` 只改配置(下次不再启动),
要停当前进程得显式 `hermes egress stop`。
注释还记了一个容易犯的错:**不要用私有的 `_read_pid()` 判断"是否在跑"**,
因为它只能证明 pidfile 非空——上一次崩溃留下的陈旧 pidfile 会让这条提示误报。
这是个小而好的判断:**"文件存在" ≠ "进程活着"**,判活要走带存活检查的公开接口。

### 3.2 令牌脱敏保留前 12 位,且短令牌**不脱敏**

`hermes_cli/proxy_cli.py:900-903 @ 863e313`

```python
def _redact_token(token: str) -> str:
    if len(token) < 16:
        return token
    return f"{token[:12]}…{token[-4:]}"
```

**◇-2**:短于 16 字符的令牌**原样打印**。这在本文件的用法下是合理的
(`status` 默认不显示令牌,要显式 `--show-tokens`),但这个函数的名字
`_redact_token` 承诺的是"脱敏",而它对短输入**什么都不做**。
若被复用到别处(如日志),这是一个会失效的脱敏器。
**本卷未发现它被本文件之外调用**——搜索面:基线全仓 `*.py`,模式 `_redact_token`,
命中仅本文件的定义处与 `format_status_text` 内的使用。

保留前 12 位也偏多:对有固定前缀的令牌格式,12 位可能覆盖不了随机段。
不判 ■,因为它只用于用户自己终端上的 `--show-tokens` 输出。

---

## 4. 逐文件角色(本卷 1 个文件 / 903 行)

| 文件 | 行 | 角色 |
|---|---|---|
| `hermes_cli/proxy_cli.py` | 903 | `hermes egress` 的命令面:8 个子命令的 argparse 注册与处理函数,其中 44% 是 `cmd_setup` 交互向导;真实代理逻辑在 `agent/proxy_sources/iron_proxy`(未读) |

---

## 5. 记号与移交

- **▲ 0**;**■ 0**(本卷为 L2 结构级,未做逐分支精读,不下缺陷判定)。
- **◇ 2**:见 §1(命名消歧只在 docstring 里)与 §3.2(短令牌不脱敏)。
- **移交(带锚点)**:`agent/proxy_sources/iron_proxy.py`(2,494 行)是 egress 代理的实现本体,
  现属 `UNCLAIMED` 桶(见 `notes/r8d-02-coverage-audit.md`),**本轮未读**;
  现象是本卷只能交代命令面,"出站流量到底被怎么约束"这个问题**在本轮没有答案**。
