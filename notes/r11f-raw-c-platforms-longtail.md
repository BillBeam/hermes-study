# R11F 片 C 底稿 —— `plugins/platforms/` 长尾 14 家的接入面

> 底稿定位:求全求证。凡对 hermes-agent 的断言紧跟 `路径:行号 @ 863e313` 与代码原文块。
> 范围 = `data/r11f/slices/C.txt` 的 59 文件 / 25,334 行,即 `plugins/platforms/` 除
> discord/telegram/slack/feishu/matrix/google_chat/wecom/dingtalk 之外的**全部 14 家**:
> photon、a2a、whatsapp、line、buzz、teams、simplex、mattermost、email、irc、raft、
> ntfy、homeassistant、sms。
> 深度 = **L2 结构级理解**:读接口面而不读实现体,所以**可以不读实现,但不能抽样接口**。

## 0. 一句话结论

平台插件的接缝不是一张表,是六个面。

本片的核心产出是**把这六个面逐项列全**(§4):清单面(`plugin.yaml` 8 键)、
env 面(110 条声明 / 113 条读取)、注册面(`PlatformEntry` 22 字段 × 14 家 = 308 格)、
契约面(`BasePlatformAdapter` 126 成员)、`ctx.*` 注册调用面(4 种)、
以及基类用 `getattr` 读的**类属性鸭子面**(方法表里根本看不见)。

**这六个面由互不知情的多个消费者分头读取** —— 光 `plugin.yaml` 就有两个消费者、
各读各的键子集(§4.1)。这正是本片两处缺陷的共同形状:
**一份手写的枚举清单,与它所枚举的东西各自演化**(§7.1 的 sidecar 镜像清单是最干净的一例)。

---

## 1. 方法与探针

六支探针,全部是**纯 AST / YAML 解析,不 import 不执行基线代码**(平台适配器的顶层
import 会拉起 aiohttp / websockets / httpx 等可选依赖,而基线的可选依赖是惰性安装的
——见 CLAUDE.md「惰性安装纪律」。凡执行基线代码的命令一律带
`HERMES_DISABLE_LAZY_INSTALLS=1`,本片全部命令都带)。

| 探针 | 枚举什么 |
|---|---|
| `data/r11f/probes/c_rollcall.py` | 59 文件点名底料(清单直接读 `slices/C.txt`,不靠记忆) |
| `data/r11f/probes/c_adapter_contract.py` | `BasePlatformAdapter` 成员 × 14 家覆写矩阵 |
| `data/r11f/probes/c_manifest_seam.py` | 14 份 `plugin.yaml` 的键集 / env 条目 / 子字段 |
| `data/r11f/probes/c_register_seam.py` | `ctx.register_platform()` 的 kwargs × `PlatformEntry` 字段 |
| `data/r11f/probes/c_env_seam.py` | 声明的 env vs 源码实际读取的 env |
| `data/r11f/probes/c_required_env_split.py` | 同一件事的两处声明是否一致 |

片内规模:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_rollcall.py --counts
```

```text
files=59
lines=25334
missing_from_baseline=0
platforms=14
platform_names=a2a,buzz,email,homeassistant,irc,line,mattermost,ntfy,photon,raft,simplex,sms,teams,whatsapp
```

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_rollcall.py --bykind
```

```text
py         files= 35 lines= 22581
yaml       files= 14 lines=   684
md         files=  4 lines=   516
mjs        files=  4 lines=  1526
gitignore  files=  1 lines=     2
json       files=  1 lines=    25
```

---

## 2. 点名表(判据 1)—— 59 个文件逐个全路径

### 2.1 归组叙述的两组同型薄文件(组内仍逐个列全路径)

**组 A:12 个字节相同的 `__init__.py`(各 3 行)。** 它们不是"差不多",是**md5 完全相同**
的同一行代码 `from .adapter import register`。插件包的 Python 面只要求一件事:
包顶层能拿到 `register`。

```verify
md5sum /home/user/hermes-agent/plugins/platforms/{buzz,email,homeassistant,irc,line,mattermost,ntfy,raft,simplex,sms,teams,whatsapp}/__init__.py | cut -d" " -f1 | sort -u
```

```text
f249b7ff9f0b9e44092963aa540c2600
```

组 A 全路径:`plugins/platforms/buzz/__init__.py`、`plugins/platforms/email/__init__.py`、
`plugins/platforms/homeassistant/__init__.py`、`plugins/platforms/irc/__init__.py`、
`plugins/platforms/line/__init__.py`、`plugins/platforms/mattermost/__init__.py`、
`plugins/platforms/ntfy/__init__.py`、`plugins/platforms/raft/__init__.py`、
`plugins/platforms/simplex/__init__.py`、`plugins/platforms/sms/__init__.py`、
`plugins/platforms/teams/__init__.py`、`plugins/platforms/whatsapp/__init__.py`。

两个**不属于**组 A 的 `__init__.py`:`plugins/platforms/a2a/__init__.py`(138 行,
`register()` 本体在这里而不在 adapter.py,并额外调 `register_tools`)、
`plugins/platforms/photon/__init__.py`(4 行,只有模块 docstring + 同一句 import)。

**组 B:14 份 `plugin.yaml` 清单(684 行)。** 每份的键集见 §4.1 的全表(逐份列全)。
全路径:`plugins/platforms/{a2a,buzz,email,homeassistant,irc,line,mattermost,ntfy,photon,raft,simplex,sms,teams,whatsapp}/plugin.yaml` —— 逐个写开即
`plugins/platforms/a2a/plugin.yaml`、`plugins/platforms/buzz/plugin.yaml`、
`plugins/platforms/email/plugin.yaml`、`plugins/platforms/homeassistant/plugin.yaml`、
`plugins/platforms/irc/plugin.yaml`、`plugins/platforms/line/plugin.yaml`、
`plugins/platforms/mattermost/plugin.yaml`、`plugins/platforms/ntfy/plugin.yaml`、
`plugins/platforms/photon/plugin.yaml`、`plugins/platforms/raft/plugin.yaml`、
`plugins/platforms/simplex/plugin.yaml`、`plugins/platforms/sms/plugin.yaml`、
`plugins/platforms/teams/plugin.yaml`、`plugins/platforms/whatsapp/plugin.yaml`。

### 2.2 逐个点名:其余 33 个文件

| # | 全路径 | 行 | 一句话角色 |
|---|---|---:|---|
| 1 | `plugins/platforms/a2a/DESIGN.md` | 165 | a2a 的设计说明:为什么把客户端工具与入站适配器放同一插件 |
| 2 | `plugins/platforms/a2a/README.md` | 90 | a2a 的用户向说明(Agent-to-Agent 协议接入) |
| 3 | `plugins/platforms/a2a/__init__.py` | 138 | a2a 插件入口:`register()` 本体 + 调 `register_tools()` |
| 4 | `plugins/platforms/a2a/adapter.py` | 1272 | 入站适配器:把 Hermes 暴露成一个可被别的 agent 发现/调用的 A2A 端点 |
| 5 | `plugins/platforms/a2a/protocol.py` | 842 | A2A 协议层:Agent Card 构造、JSON-RPC 收发、任务存储、会话落盘 |
| 6 | `plugins/platforms/a2a/security.py` | 372 | A2A 安全原语,入站适配器与客户端工具共用 |
| 7 | `plugins/platforms/a2a/tools.py` | 595 | A2A **客户端**工具(5 个),让 Hermes 作为对等方去调别的 agent |
| 8 | `plugins/platforms/buzz/adapter.py` | 1528 | Buzz(Block 的 Nostr 系人机协作平台)适配器:WS 中继 + buzz CLI |
| 9 | `plugins/platforms/buzz/nostr_auth.py` | 230 | 零依赖的 Nostr 签名,用于 Buzz WebSocket 鉴权 |
| 10 | `plugins/platforms/email/adapter.py` | 1318 | Email 适配器:IMAP 收 / SMTP 发,纯 stdlib |
| 11 | `plugins/platforms/homeassistant/adapter.py` | 604 | Home Assistant 适配器:WS 事件总线订阅 + REST 持久化通知 |
| 12 | `plugins/platforms/irc/adapter.py` | 995 | IRC 适配器:裸 TCP(`asyncio.open_connection`),纯 stdlib |
| 13 | `plugins/platforms/line/adapter.py` | 1758 | LINE Messaging API 适配器:aiohttp webhook 收 + Push API 发 |
| 14 | `plugins/platforms/mattermost/adapter.py` | 1327 | Mattermost 适配器:WebSocket 事件 + REST 发帖 |
| 15 | `plugins/platforms/ntfy/adapter.py` | 617 | ntfy 适配器:HTTP 流订阅 topic + HTTP POST 发布,只用 httpx |
| 16 | `plugins/platforms/photon/README.md` | 211 | photon 插件说明(iMessage via Photon Spectrum) |
| 17 | `plugins/platforms/photon/adapter.py` | 2910 | 本片最大适配器:管理 Node sidecar 进程 + 与之通过本地 HTTP 对话 |
| 18 | `plugins/platforms/photon/auth.py` | 1163 | Photon Dashboard API 客户端 + device-code 登录流程 |
| 19 | `plugins/platforms/photon/cli.py` | 540 | `hermes photon ...` 子命令,经 `ctx.register_cli_command()` 注册 |
| 20 | `plugins/platforms/photon/sidecar_paths.py` | 141 | 决定 sidecar 从哪个目录运行、Node 依赖装在哪(只读安装树时镜像到数据卷) |
| 21 | `plugins/platforms/photon/sidecar/.gitignore` | 2 | 忽略 `node_modules/` 与 npm 错误日志 |
| 22 | `plugins/platforms/photon/sidecar/README.md` | 50 | sidecar 自身的说明 |
| 23 | `plugins/platforms/photon/sidecar/index.mjs` | 1241 | sidecar 主体:12 条本地 HTTP 路由 + spectrum-ts 长连接 |
| 24 | `plugins/platforms/photon/sidecar/package.json` | 25 | sidecar 的 npm 清单(依赖 spectrum-ts 等) |
| 25 | `plugins/platforms/photon/sidecar/patch-spectrum-mixed-attachments.mjs` | 178 | 打补丁:上游 spectrum-ts 的混合附件入站映射 |
| 26 | `plugins/platforms/photon/sidecar/send-format.mjs` | 27 | 纯函数:出站 `/send` 该用哪种 builder |
| 27 | `plugins/platforms/photon/sidecar/stream-staleness.mjs` | 80 | 纯函数:半开 gRPC「僵尸流」看门狗的判定规则 |
| 28 | `plugins/platforms/raft/adapter.py` | 852 | Raft 适配器:本地 aiohttp 唤醒端点 + raft CLI;**不碰消息体** |
| 29 | `plugins/platforms/simplex/adapter.py` | 1382 | SimpleX Chat 适配器:WebSocket 连本地 simplex-chat CLI |
| 30 | `plugins/platforms/sms/adapter.py` | 536 | SMS(Twilio)适配器:aiohttp webhook 收 + Twilio REST 发 |
| 31 | `plugins/platforms/teams/adapter.py` | 1503 | Microsoft Teams 适配器:microsoft-teams-apps SDK + aiohttp 桥 |
| 32 | `plugins/platforms/whatsapp/adapter.py` | 1918 | WhatsApp 适配器:管理 Node.js bridge 子进程 |

**点名合计**:组 A(12 个 `__init__.py`)+ 组 B(14 份 `plugin.yaml`)
+ 上表 32 项 + `plugins/platforms/photon/__init__.py`(§2.1 末段单独点名,不在上表内)
= 12 + 14 + 32 + 1 = **59**,与 `--counts` 的 `files=59` 相符。
上表第 3 项 `plugins/platforms/a2a/__init__.py` 已计入这 32 项之内。

**判据 1 的机械复核**:把 `slices/C.txt` 的 59 条路径逐条拿去本文件里找,
**必须 59 条全部命中**。这条检查对"我以为我点过了"免疫 —— 清单来自切片文件,
不来自记忆。

```verify
python3 -c "
import pathlib
note=pathlib.Path('notes/r11f-raw-c-platforms-longtail.md').read_text(encoding='utf-8')
paths=[l.rsplit(chr(9),1)[0] for l in pathlib.Path('data/r11f/slices/C.txt').read_text().splitlines() if l.strip()]
missing=[p for p in paths if p not in note]
print('slice_files=%d' % len(paths)); print('named_in_note=%d' % (len(paths)-len(missing))); print('MISSING=%d' % len(missing))
"
```

```text
slice_files=59
named_in_note=59
MISSING=0
```

---

## 3. 接入形态分类(判据 2 的组织框架)

14 家的跨度很大。按**入站消息从哪来**分成五类,每类的接缝差异不同:

| 形态 | 平台 | 入站机制 | 接缝差异 |
|---|---|---|---|
| **A 长连接客户端** | mattermost、homeassistant、simplex、buzz | 适配器主动连出去,拿 WebSocket | 无需对外暴露端口;`connect()` 里做重连/心跳 |
| **B 轮询 / HTTP 流** | ntfy、photon、teams | 适配器主动连出去,拿 HTTP 长流或轮询 | 同 A,但无 WS 协议栈依赖 |
| **C 本地监听端口** | line、sms、raft、a2a | 适配器**自己起一个 HTTP server** 收 webhook | 多一层「谁能打进来」的鉴权面(HMAC / token) |
| **D 子进程 sidecar** | photon、whatsapp、buzz、simplex、raft | 拉起一个外部进程(Node / CLI),与之本地通信 | 多一层**进程生命周期 + 文件布局**接缝(见 §7.1 的缺陷) |
| **E 老协议直连** | email、irc | stdlib 直接说协议(IMAP/SMTP、裸 TCP) | 零第三方依赖,但重连/编码/限速全自己写 |

**形态 D 多出来的那层接缝长什么样**:photon 的 sidecar 是一个独立 Node 进程,
适配器与它之间的契约是一组**本地 HTTP 路由**(共 12 条),
即"插件的对外接缝"在这一形态下还要再嵌套一层进程间协议:

```verify
grep -oE 'req\.url === "/[a-z-]+"' /home/user/hermes-agent/plugins/platforms/photon/sidecar/index.mjs | sort -u | sed 's/req.url === //'
```

```text
"/healthz"
"/inbound"
"/probe"
"/react"
"/send"
"/send-attachment"
"/send-effect"
"/send-poll"
"/send-richlink"
"/shutdown"
"/typing"
"/unreact"
```

形态不是互斥的:photon 同时属于 B 与 D(sidecar 起进程,再用本地 HTTP 与它对话);
buzz 同时属于 A 与 D。**这正是本片值得记的一点**:`BasePlatformAdapter` 这个 ABC
对入站形态**完全不表态** —— 它只要求 `connect/disconnect/send/get_chat_info` 四个方法,
"消息从哪来"整个是适配器的私事。所以 14 家能长成五种完全不同的东西而共用一个契约。

机械依据(各平台源码里出现的传输原语):

```verify
for p in photon a2a whatsapp line buzz teams simplex mattermost email irc raft ntfy homeassistant sms; do printf "%-14s " "$p"; grep -ohE "websockets\.connect|ws_connect|imaplib|smtplib|asyncio\.open_connection|ThreadingHTTPServer|aiohttp\.web|httpx\.AsyncClient|create_subprocess_exec" /home/user/hermes-agent/plugins/platforms/$p/*.py 2>/dev/null | sort -u | tr '\n' ' '; echo; done
```

```text
photon         httpx.AsyncClient 
a2a            ThreadingHTTPServer 
whatsapp       
line           aiohttp.web 
buzz           create_subprocess_exec websockets.connect 
teams          httpx.AsyncClient 
simplex        
mattermost     ws_connect 
email          imaplib smtplib 
irc            asyncio.open_connection 
raft           
ntfy           httpx.AsyncClient 
homeassistant  ws_connect 
sms            aiohttp.web 
```

*读数口径:whatsapp / simplex / raft 三行为空,不代表它们没有传输 —— 它们用的原语不在
上面这份**固定模式表**里(whatsapp 用 `subprocess` 起 Node bridge、simplex 用
`websockets` 但走的是 import 后的别名、raft 用 `web.Application`)。这条命令能证明的
只是「出现了哪些**表上的**原语」,**不能**用来证明「没出现的就没有」——
那需要另一次搜索面。形态分类以逐个读 `connect()` 为准,不以这条命令为准。*

---

## 4. 接缝穷举(判据 2 —— 本片重心)

### 4.1 清单面:14 份 `plugin.yaml` 的顶层键

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_manifest_seam.py --counts
```

```text
manifests=14
distinct_top_keys=8
unread_top_keys=0
requires_env_entries=25
optional_env_entries=85
distinct_env_names=110
```

**全表(逐份列全,不抽样)** —— `reader` 列是该键被哪个消费者真的 `get()` 过:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_manifest_seam.py --keymatrix
```

```text
key                      reader   n phot  a2a what line buzz team simp matt emai  irc raft ntfy home  sms
author                  plugins  14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
description             plugins  14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
kind                    plugins  14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
label                    config  14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
name                  plugins+config  14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
optional_env             config  13    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    Y    Y
requires_env          plugins+config  14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
version                 plugins  14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
```

**读法(这是本片对清单面最重要的一句)**:14 份 manifest 只用了**同一套 8 个键**,
而这 8 个键被**两个互不知情的消费者**分头读走:

**消费者一** —— `hermes_cli/plugins.py:1585` 的 `_parse_manifest`,读 8 键产出 `PluginManifest`:

`hermes_cli/plugins.py:1657 @ 863e313`

```
            return PluginManifest(
                name=name,
                version=str(data.get("version", "")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                requires_env=data.get("requires_env", []),
                provides_tools=data.get("provides_tools", []),
                provides_hooks=data.get("provides_hooks", []),
```

**消费者二** —— `hermes_cli/config.py:5363` 的 `_inject_platform_plugin_env_vars`,
读 4 键产出设置向导的输入面:

`hermes_cli/config.py:5395 @ 863e313`

```
            label = manifest.get("label") or manifest.get("name") or child.name
            # Merge required + optional env var declarations.
            entries = list(manifest.get("requires_env") or [])
            entries.extend(manifest.get("optional_env") or [])
```

于是 `label` 与 `optional_env` **完全不进 `PluginManifest`**(`hermes_cli plugins list`
看不到 label),而 `kind/version/author` **完全不进设置向导**。派工书给的全仓 15 键里,
`hooks`/`provides_web_providers`/`pip_dependencies` 等**本片一份都没用**,
所以本片 `unread_top_keys=0` —— 长尾平台插件的清单用法是全仓里最规整的一档。

### 4.2 env 面:`requires_env` / `optional_env`

25 条 required + 85 条 optional = **110 个不同变量名**。每条的子字段实际用到 **6 个**
(派工书列了 5 个,基线里还有第 6 个 `category`):

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_manifest_seam.py --envfields
```

```text
 110  description
 110  name
 110  password
 110  prompt
   7  url
   1  category
```

`name`/`description`/`prompt`/`password` **110/110 全覆盖**——没有一条用"裸字符串"简写形式,
尽管注入器明确支持裸字符串简写:

`hermes_cli/config.py:5400 @ 863e313`

```
                if isinstance(entry, str):
                    name = entry
                    meta: dict = {}
                elif isinstance(entry, dict) and entry.get("name"):
                    name = entry["name"]
```
`category` 只有 1 处,即 raft 的 `RAFT_PROFILE`(把它归到 `setting` 而非默认的 `messaging`)。

**逐条变量名全表**见 `data/r11f/c/env-entries.txt`(由 `--env` 生成,110 条逐条列全)。

**password 启发式的负结论**:对未显式声明的变量按后缀自动判密 ——

`hermes_cli/config.py:5410 @ 863e313`

```
                # Heuristic: anything named *TOKEN, *SECRET, *KEY, *PASSWORD
                # is a password field unless explicitly overridden.
                name_upper = name.upper()
                is_secret = bool(meta.get("password") or meta.get("secret"))
                if not is_secret and not meta.get("password") is False:
                    is_secret = any(
                        name_upper.endswith(suf)
                        for suf in ("_TOKEN", "_SECRET", "_KEY", "_PASSWORD", "_JSON")
```

注意 `if not is_secret and not meta.get("password") is False:` 这一句:
**显式写了 `password: false` 就跳过启发式**。所以若某变量名带上述后缀
**却显式写了 `password: false`**,它会以明文显示。本片实测**零命中**:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_manifest_seam.py --secretcheck; echo "exit=$?"
```

```text
exit=0
```

*搜索面:14 份 manifest 的 `requires_env` + `optional_env` 全部 110 条,按
`hermes_cli/config.py:5407-5416` 的原口径复算(先 `password or secret`,再后缀启发式),
输出「看起来像密钥但判定为非密钥」的条目。零输出 = 无一条命中。
本检查**不覆盖**片外的 8 家平台,也不覆盖非平台插件。*

### 4.3 注册面:`ctx.register_platform()` × `PlatformEntry`

平台插件往宿主注册能力的入口是 `register(ctx)`,它调 `register_platform`:

`hermes_cli/plugins.py:953 @ 863e313`

```
    def register_platform(
        self,
        name: str,
        label: str,
        adapter_factory: Callable,
```

该方法只显式接 8 个形参,其余 `**entry_kwargs` **原样转发**给下面这个数据类,
**未知键由 dataclass 构造器抛 TypeError**:

`gateway/platform_registry.py:38 @ 863e313`

```
@dataclass
class PlatformEntry:
    """Metadata and factory for a single platform adapter."""
```

所以「注册面」= `PlatformEntry` 的全部字段。

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_register_seam.py --counts
```

```text
entry_fields=22
platforms=14
cells=308
fields_never_passed=2
never_passed=source,plugin_name
kwargs_not_entry_fields=(none)
kwargs_passed_total=232
```

**22 字段 × 14 家 = 308 格全表(逐项列全)**:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_register_seam.py --matrix
```

```text
PlatformEntry field          kind  n phot  a2a what line buzz team simp matt emai  irc raft ntfy home  sms
name                     required 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
label                    required 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
adapter_factory          required 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
check_fn                 required 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
validate_config           default 10    Y    Y    .    Y    Y    Y    Y    Y    .    Y    .    Y    Y    .
is_connected              default 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
required_env              default 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
install_hint              default 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
setup_fn                  default 10    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    Y    .    .    .
source                    default  0    .    .    .    .    .    .    .    .    .    .    .    .    .    .
plugin_name               default  0    .    .    .    .    .    .    .    .    .    .    .    .    .    .
allowed_users_env         default 12    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    .    Y
allow_all_env             default 12    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    .    Y
max_message_length        default 11    Y    .    Y    Y    .    Y    Y    Y    Y    Y    .    Y    Y    Y
pii_safe                  default  8    Y    .    .    Y    Y    .    Y    .    Y    Y    .    Y    .    Y
emoji                     default 14    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
allow_update_command      default 13    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    Y    Y
platform_hint             default  9    Y    Y    .    Y    Y    Y    Y    .    .    Y    Y    Y    .    .
env_enablement_fn         default  8    Y    .    .    Y    Y    Y    Y    .    .    Y    Y    Y    .    .
apply_yaml_config_fn      default  3    .    .    Y    .    Y    .    .    Y    .    .    .    .    .    .
cron_deliver_env_var      default 12    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    .    Y
standalone_sender_fn      default 12    Y    .    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    Y    Y
```

**读法**:

- **4 个必填**(`name/label/adapter_factory/check_fn`)14/14 —— 这是硬契约。
- **`source` / `plugin_name` 0/14**:不是"没人用",而是**插件不许自己填** ——
  由宿主自己填。**这是身份字段,由宿主而不是被注册方声明**,是一条值得抄的设计:

  `hermes_cli/plugins.py:987 @ 863e313`

  ```
          entry_kwargs.setdefault("plugin_name", self.manifest.name)
          entry = PlatformEntry(
              name=name,
              label=label,
              adapter_factory=adapter_factory,
              check_fn=check_fn,
              validate_config=validate_config,
              required_env=required_env or [],
              install_hint=install_hint,
              source="plugin",
              **entry_kwargs,
          )
  ```
- **`is_connected` 14/14 却是 `default`**:字段声明可选,实际全员必传。
  说明这个"可选"是历史包袱,不是设计意图。
- **两个洼地**:`raft` 只传 11 项、`homeassistant` 只传 12 项,都缺
  `allowed_users_env`/`allow_all_env`(见 §7.2)。
- **`apply_yaml_config_fn` 只有 3 家**(whatsapp/buzz/mattermost):
  这是"把 `config.yaml` 里本平台的键翻译成环境变量"的钩子,是核心把平台知识
  **推回插件**的机制 —— 核心里留下的只是一条注释:

  `gateway/config.py:1723 @ 863e313`

  ```
              # Mattermost config bridge moved into plugins/platforms/mattermost/
              # adapter.py::_apply_yaml_config — see #25443 (apply_yaml_config_fn).
  ```

  **没传这个钩子的 11 家,
  它们的配置桥仍然写在核心里**(见 §7.2 的 homeassistant 例)。

逐平台的实参值见 `data/r11f/c/register-values.txt`(由 `--values` 生成)。

### 4.4 契约面:`BasePlatformAdapter` 126 个成员

ABC 在 `gateway/platforms/base.py:2629`。

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_adapter_contract.py --counts
```

```text
base_members=126
abstract=4
overridden_optional=22
inherited_untouched=100
platforms=14
contract_cells=364
additions_total=205
additions_public=11
```

**(a) 抽象方法 4 个 —— 14/14 全实现,56 格无一空缺**:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_adapter_contract.py --abstract
```

```text
base_line kind          member                             phot  a2a what line buzz team simp matt emai  irc raft ntfy home  sms
     3471 async def     connect                               Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
     3491 async def     disconnect                            Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
     6671 async def     get_chat_info                         Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
     3496 async def     send                                  Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
```

**这就是"接一个新平台的最小成本":四个方法。** 一个 126 成员的基类只把 4 个设成抽象,
其余 122 个都给了能用的默认实现 —— 长尾平台(raft 只覆写 2 个可选项、
ntfy/homeassistant/sms 各 2 个)因此能只写几百行就接上。

**(b) 被覆写的可选面 22 个 × 14 家 = 308 格全表**:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_adapter_contract.py --overridden
```

```text
base_line kind          member                             phot  a2a what line buzz team simp matt emai  irc raft ntfy home  sms
     2750 def           __init__                              Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    Y
     4973 staticmethod  _is_retryable_error                   Y    .    .    .    .    .    .    .    .    .    .    .    .    .
     4677 async def     _keep_typing                          .    .    .    Y    .    .    .    .    .    .    .    .    .    .
     5042 async def     _send_with_retry                      Y    .    .    .    .    .    .    .    .    .    .    .    .    .
     2912 property      authorization_is_upstream             .    Y    .    .    .    .    .    .    .    .    .    .    .    .
     3552 async def     edit_message                          .    .    Y    .    .    .    .    Y    .    .    .    .    .    .
     6681 def           format_message                        Y    .    .    Y    .    .    .    Y    .    .    .    .    .    Y
     5554 async def     handle_message                        .    .    .    .    .    .    .    .    .    .    Y    .    .    .
     4808 async def     interrupt_session_activity            .    .    .    Y    .    .    .    .    .    .    .    .    .    .
     3293 property      name                                  .    Y    .    .    Y    .    .    .    .    Y    .    .    .    .
     4928 async def     on_processing_complete                .    Y    .    .    .    .    .    .    .    .    .    .    .    .
     4925 async def     on_processing_start                   Y    .    .    .    .    .    .    .    .    .    .    .    .    .
     3991 async def     send_animation                        Y    .    .    .    .    .    .    .    .    .    .    .    .    .
     3780 async def     send_clarify                          Y    .    Y    .    .    .    .    .    .    .    .    .    .    .
     4232 async def     send_document                         Y    .    Y    .    .    Y    Y    Y    Y    .    .    .    .    .
     3972 async def     send_image                            Y    .    Y    .    Y    Y    Y    Y    Y    .    .    .    .    .
     4305 async def     send_image_file                       Y    .    Y    Y    .    Y    Y    Y    .    .    .    .    .    .
     3915 async def     send_multiple_images                  .    .    .    .    .    .    .    Y    Y    .    .    .    .    .
     3874 async def     send_typing                           Y    Y    Y    Y    Y    Y    Y    Y    Y    Y    .    Y    Y    .
     4205 async def     send_video                            Y    .    Y    Y    .    Y    Y    Y    .    .    .    .    .    .
     4062 async def     send_voice                            Y    .    Y    Y    .    Y    Y    Y    .    .    .    .    .    .
     3883 async def     stop_typing                           Y    .    .    .    .    .    .    .    .    .    .    .    .    .
```

**读法**:

- **`send_typing` 12/14 是覆写率最高的可选方法**,高于任何媒体方法。
  "正在输入"这个纯粹的体验细节,比发图发视频更普遍地需要平台定制。
- **4 个私有基类成员被覆写**(`_is_retryable_error`、`_keep_typing`、
  `_send_with_retry`、`__init__` 不算):photon 覆写 `_send_with_retry`
  与 `_is_retryable_error`,line 覆写 `_keep_typing`。带下划线的基类方法
  **事实上是公开扩展点**,而基类没有任何地方声明它们是。这是契约的**隐性部分**。
- **`handle_message` 只有 raft 覆写**。这是入站主干(基类 200 行的调度逻辑),
  覆写它意味着 raft 绕过了默认调度 —— 与它 "不碰消息体、只发内容无关的唤醒提示"
  的定位一致。
- **`authorization_is_upstream` 只有 a2a 覆写**:声明"鉴权由可信上游做完了"。

**(c) 100 个从未被这 14 家碰过的成员** —— 全表见 `data/r11f/c/inherited-untouched.txt`
(由 `--inherited` 生成,100 行逐个列全)。这一百个是**默认行为面**:媒体提取
(`extract_media`/`extract_images`/`extract_local_files`)、流式 TTS 五件套、
文本消抖、会话锁、审批格式化…… 全部由基类统一提供,长尾适配器一行不写就有。

**(d) 各家新增的成员共 205 个,其中 public 仅 11 个** —— 说明适配器的自有面
几乎全是私有实现细节,没有形成"第二套对外 API"。

### 4.5 `ctx.*` 注册调用的全面(不止 `register_platform`)

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_register_seam.py --fields | head -4
```

```text
name                     required  used_by=14
label                    required  used_by=14
adapter_factory          required  used_by=14
check_fn                 required  used_by=14
```

除 `register_platform` 外,片内还有三种注册调用:

| 调用 | 谁用 | 条数 | 锚点 |
|---|---|---:|---|
| `ctx.register_platform` | 全部 14 家 | 14 | `plugins/platforms/ntfy/adapter.py:581`:`ctx.register_platform(` |
| `ctx.register_hook` | 仅 raft | 7 | `plugins/platforms/raft/adapter.py:846`:`ctx.register_hook("on_session_start", _on_session_start)` |
| `ctx.register_tool` | 仅 a2a | 1 处调用 → 注册 5 个工具 | `plugins/platforms/a2a/tools.py:588`:`ctx.register_tool(` |
| `ctx.register_cli_command` | 仅 photon | 1 | `plugins/platforms/photon/adapter.py:2905`:`ctx.register_cli_command(` |

raft 注册的 7 个钩子取自宿主的钩子白名单 ——

`hermes_cli/plugins.py:135 @ 863e313`

```
VALID_HOOKS: Set[str] = {
    "pre_tool_call",
    "post_tool_call",
    "transform_terminal_output",
    "transform_tool_result",
```

—— 覆盖会话 / LLM / 工具全生命周期:`on_session_start`、`pre_llm_call`、
`pre_tool_call`、`post_tool_call`、`post_llm_call`、`on_session_end`、`on_session_finalize`。
**一个"平台"插件同时是一个全生命周期观察者** —— 这是 `kind: platform`
这个分类挡不住的能力越界面(◇,见 §7.4)。

a2a 注册的 5 个工具:

`plugins/platforms/a2a/tools.py:576 @ 863e313`

```
_HANDLERS = {
    "a2a_discover": a2a_discover,
    "a2a_call": a2a_call,
    "a2a_list": a2a_list,
    "a2a_history": a2a_history,
    "a2a_orchestrate": a2a_orchestrate,
}
```

统一挂在 `toolset="a2a"` 下。**a2a 因此是片内唯一双向的插件**:
既让别人调 Hermes(adapter.py),也让 Hermes 调别人(tools.py)。

**这里有一条方法论教训(与 CLAUDE.md「机械判据不得用词根去判语义」同源)。**
朴素 grep 会多数:

```verify
grep -rhoE "ctx\.register_[a-z_]+\(" /home/user/hermes-agent/plugins/platforms/{photon,a2a,whatsapp,line,buzz,teams,simplex,mattermost,email,irc,raft,ntfy,homeassistant,sms}/*.py | sort | uniq -c | sort -rn
```

```text
     15 ctx.register_platform(
      7 ctx.register_hook(
      2 ctx.register_cli_command(
      1 ctx.register_tool(
```

grep 报 15 个 `register_platform` 与 2 个 `register_cli_command`,AST 只认 14 与 1。
差的两处是 **docstring 里提到了这个调用名** ——

`plugins/platforms/simplex/adapter.py:140 @ 863e313`

```
    Instantiated by the ``adapter_factory`` passed to
    ``ctx.register_platform()`` in :func:`register`.
```

`plugins/platforms/photon/cli.py:2 @ 863e313`

```
``hermes photon ...`` CLI subcommands — registered by the plugin via
``ctx.register_cli_command()``.
```

**上面那张表的条数用的是 AST 读数,不是 grep 读数。**

### 4.6 鸭子类型的类属性面(方法之外的第五张表)

契约不止方法。基类用 `getattr` 从适配器实例上读**类属性**,而这些属性
**基类自己并不定义**,所以它们不在 §4.4 的 126 个成员里。

`gateway/platforms/base.py:2869 @ 863e313`

```
        try:
            return int(getattr(self, "MAX_MESSAGE_LENGTH", 4096) or 4096)
        except (TypeError, ValueError):
            return 4096
```

`gateway/platforms/base.py:2692 @ 863e313`

```
    # Whether this adapter's ``send()`` splits long content into multiple
    # messages via ``truncate_message()``.  When True, the delivery router
    # (gateway/delivery.py) skips gateway-level truncation and lets the
    # adapter chunk natively — preserving full output on platforms that
    # support multi-message delivery (Discord, Telegram, …).  Default False
    # (conservative); adapters verified to chunk in ``send()`` set True.
    splits_long_messages: bool = False
```

片内 `splits_long_messages = True` 的只有 **3 家**(teams、mattermost、whatsapp);
另外 11 家保持默认 False,由投递路由在网关侧截断:

`gateway/delivery.py:502 @ 863e313`

```
            # Step 2 — truncation (only for non-chunking adapters).
            if getattr(adapter, "splits_long_messages", False):
                # Adapter chunks natively — deliver full payload.
```
`MAX_MESSAGE_LENGTH` 类属性由 6 家设置(photon/teams/simplex/homeassistant/sms/ntfy),
其余 8 家吃 4096 的兜底默认。

**注意这是两个独立的长度声明**:`PlatformEntry.max_message_length`(注册面,11/14 传,
供 relay descriptor 用)与适配器类属性 `MAX_MESSAGE_LENGTH`(运行期,
供 `max_message_length_for_chat` 用)。**同名不同物**,而没有任何机制核对两者一致。

### 4.7 同一件事的两处声明:`requires_env` vs `required_env`

「这个平台必须有哪些环境变量」在两处各声明一遍,走两条互不相交的消费链:

- `plugin.yaml: requires_env` → `_parse_manifest` → `PluginManifest` → 设置向导;
- `register_platform(required_env=[...])` → `PlatformEntry.required_env` → 网关侧就绪检查。

实测**14/14 完全一致**,一个字都不差:

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_required_env_split.py --counts
```

```text
platforms=14
identical_sets=14
differing_sets=0
yaml_only_total=0
registry_only_total=0
```

这是个**好消息也是个风险点**:一致性完全靠人工维护,**没有任何检查**。
逐平台表见 `data/r11f/c/required-env-split.txt`。

### 4.8 声明的 env vs 实际读取的 env

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/c_env_seam.py --counts
```

```text
declared_total=110
read_literal_total=113
declared_and_read=72
declared_only=38
read_only=41
dynamic_reads=16
```

**38 个"声明了但插件目录下没有任何 .py 读它"** —— 这不是 bug,而是揭示了一条设计:
`*_ALLOWED_USERS`、`*_ALLOW_ALL_USERS`、`*_HOME_CHANNEL` 这些**由核心按约定读**,
插件只负责在 manifest 里声明它们好让设置向导问出来,并在
`register_platform(allowed_users_env=..., allow_all_env=..., cron_deliver_env_var=...)`
里**把变量名告诉核心**。**插件声明名字,核心执行语义。**

另一部分(`HASS_TOKEN`、`TWILIO_AUTH_TOKEN`、`EMAIL_PASSWORD`、`MATTERMOST_TOKEN`……)
走的是 `gateway/config.py` 的 env→`PlatformConfig` 桥,插件从 `config.token` /
`config.extra` 里拿,不直接读环境。

**41 个"代码在读但向导从不问"**,以及 16 处非字面量动态读取(本探针的已知下限:
只统计 `ast.Constant` 键名),逐条见 `data/r11f/c/env-read-only.txt`。

---

## 5. 端到端链(判据 3)—— ntfy 的一次完整往返

选 ntfy 是因为它 617 行、零外部 SDK、五个形态里最干净,整条链每一跳都看得见。

**场景**:用户在手机上往 `https://ntfy.sh/hermes-in` 发一条 "总结一下今天的日程"。

| # | 跳 | 锚点 |
|---|---|---|
| 1 | 用户 POST 到 ntfy 服务器的 topic | (平台侧,不在仓库内) |
| 2 | 适配器早已挂着 `/json` 长流,`poll=false` 保持连接 | `plugins/platforms/ntfy/adapter.py:262`:`async def _consume_stream(self, url: str, headers: Dict[str, str]) -> None:` |
| 3 | 流里读到一行 JSON,派发 | `plugins/platforms/ntfy/adapter.py:308`:`await self._on_message(event)` |
| 4 | 去重 + 回声标签过滤 + 空正文过滤 | `plugins/platforms/ntfy/adapter.py:332`:`async def _on_message(self, event: Dict[str, Any]) -> None:` |
| 5 | **身份决策**:`user_id` 钉死为 topic 名,拒绝用发布者可控的 `title` | `plugins/platforms/ntfy/adapter.py:351`:`user_id = topic` |
| 6 | 组装 `SessionSource`(基类提供) | `plugins/platforms/ntfy/adapter.py:360`:`source = self.build_source(` |
| 7 | 组装 `MessageEvent` | `plugins/platforms/ntfy/adapter.py:377`:`message_event = MessageEvent(` |
| 8 | **交回内核**:插件的入站责任到此为止 | `plugins/platforms/ntfy/adapter.py:387`:`await self.handle_message(message_event)` |
| 9 | 基类调度:鉴权、配对、会话锁、后台任务 | `gateway/platforms/base.py:5554`:`async def handle_message(self, event: MessageEvent) -> None:` |
| 10 | 允许名单检查(ntfy 传了 `allowed_users_env`) | `gateway/platforms/base.py:3382`:`def _is_sender_authorized(` |
| 11 | 后台跑 agent 回合 | `gateway/platforms/base.py:5786`:`async def _process_message_background(self, event: MessageEvent, session_key: str) -> None:` |
| 12 | 流式消费者按**每个 chat 的**上限切块 | `gateway/stream_consumer.py:1454`:`raw_limit = self.adapter.max_message_length_for_chat(self.chat_id)` |
| 13 | 上限来自适配器类属性,兜底 4096 | `gateway/platforms/base.py:2870`:`return int(getattr(self, "MAX_MESSAGE_LENGTH", 4096) or 4096)` |
| 14 | 逐块回调适配器 | `gateway/stream_consumer.py:1469`:`result = await self.adapter.send(` |
| 15 | 适配器发布回 topic,带 `X-Tags` 回声标记(呼应第 4 跳) | `plugins/platforms/ntfy/adapter.py:405`:`async def send(` |
| 16 | 返回 `SendResult`,内核据此决定是否重试 | `plugins/platforms/ntfy/adapter.py:446`:`return SendResult(success=True, message_id=returned_id)` |

**这条链最值得记的两点**:

1. **第 5 跳是插件唯一必须自己想清楚的安全决策**。ntfy 协议没有认证身份概念,
   适配器选择"把整个 topic 当一个可信频道",并在注释里写明**为什么不能用 `title`**。
   基类帮不了它 —— 身份从哪来,只有适配器知道。
2. **第 12–14 跳说明"切块"是内核的事,不是插件的事**(除非插件声明
   `splits_long_messages = True` 自己接管)。所以第 15 跳里 ntfy 自己的截断
   是第二道防线,正常路径下不会触发 —— 这正是 §7.2 的对照组。

---

## 6. 逐字取证(判据 4)

以下两块是**逐字**源码摘录,整块每一行与基线一致。

**块一**:photon sidecar 的镜像文件清单(§7.1 的缺陷现场)。

`plugins/platforms/photon/sidecar_paths.py:51 @ 863e313`

```
_MIRROR_FILES = (
    "index.mjs",
    "package.json",
    "package-lock.json",
    "patch-spectrum-mixed-attachments.mjs",
)
```

**块二**:同一个 sidecar 的 `index.mjs` 顶部 import —— 它 import 了上面清单里
**没有**的两个模块。

`plugins/platforms/photon/sidecar/index.mjs:68 @ 863e313`

```
import { patchSpectrumTs } from "./patch-spectrum-mixed-attachments.mjs";
import { chooseSendFormat } from "./send-format.mjs";
import {
  classifyProbeRejection,
  shouldProbe,
  isZombieSuspect,
} from "./stream-staleness.mjs";
```

**块三**:Home Assistant 的静默截断(§7.2)。

`plugins/platforms/homeassistant/adapter.py:429 @ 863e313`

```
        payload = {
            "title": "Hermes Agent",
            "message": content[:self.MAX_MESSAGE_LENGTH],
        }
```

**块四**:同一目录树下 ntfy 的对照写法 —— 同样的切片,先记一条 warning。

`plugins/platforms/ntfy/adapter.py:429 @ 863e313`

```
        if len(content) > self.MAX_MESSAGE_LENGTH:
            logger.warning(
                "[%s] Message truncated from %d to %d chars (ntfy limit)",
                self.name, len(content), self.MAX_MESSAGE_LENGTH,
            )
        body = content[:self.MAX_MESSAGE_LENGTH]
```

**块五**:Home Assistant 事件无条件放行(§7.3)。

`gateway/authz_mixin.py:398 @ 863e313`

```
        # Home Assistant events are system-generated (state changes), not
        # user-initiated messages.  The HASS_TOKEN already authenticates the
        # connection, so HA events are always authorized.
        # Webhook events are authenticated via HMAC signature validation in
        # the adapter itself — no user allowlist applies.
        if source.platform in {Platform.HOMEASSISTANT, Platform.WEBHOOK}:
            return True
```

---

## 7. 记号(判据 5)

### 7.1 ■ `H-R11F-C-a` —— photon sidecar 的镜像清单漏了两个它自己 import 的模块

**现象**:`plugins/platforms/photon/sidecar_paths.py:51` 的 `_MIRROR_FILES` 列了 4 个文件,
而 `plugins/platforms/photon/sidecar/index.mjs:69` 与 `:70` 分别 import 了
`./send-format.mjs` 和 `./stream-staleness.mjs` —— **两者都不在清单里**(见 §6 块一/块二)。

**为什么会出事**:`resolve_sidecar_dir()` 在安装树只读时把 sidecar 镜像到数据卷,
**只复制 `_MIRROR_FILES` 里的文件**:

`plugins/platforms/photon/sidecar_paths.py:125 @ 863e313`

```
        for name in _MIRROR_FILES:
            src = source / name
            if not src.exists():
                continue
            dst = mirror / name
            if not dst.exists() or not filecmp.cmp(str(src), str(dst), shallow=False):
                shutil.copy2(str(src), str(dst))
        return mirror
```

Node 按 `index.mjs` **所在目录**解析 `./send-format.mjs`,而镜像目录里没有它,
于是 `node index.mjs` 以 `ERR_MODULE_NOT_FOUND` 起不来。
注意 `if not src.exists(): continue` 让"清单里有但磁盘上没有"也是静默的 ——
但这里的问题相反:**磁盘上有,清单里没有**,连这条静默保护都碰不到。

**触发条件**:只读安装树(托管镜像),且 `node_modules` 缺失或比 lockfile 旧 ——
即下面这个"就地跑"的分支不成立时。这正是镜像机制存在的理由,
也就是说**这条路径只在它唯一被需要的时候是坏的**。

`plugins/platforms/photon/sidecar_paths.py:111 @ 863e313`

```
    # Read-only install tree (hosted/managed image). If the image baked the
    # deps at build time and they match the lockfile, run in place — the
    # sidecar itself never writes inside its own directory.
    if (source / "node_modules").exists() and not _lock_newer_than_install(source):
        return source
```

**为什么测试没抓到**:两个模块**有**测试,但测试直接读源码树的绝对路径,
不经过镜像。全仓搜索面(排除 `node_modules`,覆盖 `.py`/`.mjs`/`.json`):

```verify
grep -rln "send-format\|stream-staleness" /home/user/hermes-agent --include=*.py --include=*.mjs --include=*.json 2>/dev/null | grep -v node_modules | sed "s|/home/user/hermes-agent/||" | sort
```

```text
plugins/platforms/photon/adapter.py
plugins/platforms/photon/sidecar/index.mjs
tests/plugins/platforms/photon/test_url_send_path.py
tests/plugins/platforms/photon/test_zombie_stream_watchdog.py
```

**`sidecar_paths.py` 不在这份名单里** —— 这就是"镜像清单从不提这两个模块"的直接证据。
`tests/plugins/platforms/photon/test_url_send_path.py:24`:`_MODULE = Path("plugins/platforms/photon/sidecar/send-format.mjs").resolve()`
钉的是源码树路径,镜像目录里缺文件与这条测试无关。

**成因(可复算)**:清单写于 `sidecar_paths.py` 最后一次改动时,两个模块**晚 5 天**才出现。

```verify
cd /home/user/hermes-agent && for f in sidecar_paths.py sidecar/send-format.mjs sidecar/stream-staleness.mjs sidecar/patch-spectrum-mixed-attachments.mjs; do printf "%-45s " "$f"; git log -1 --format="%ad" --date=short -- "plugins/platforms/photon/$f"; done
```

```text
sidecar_paths.py                              2026-07-23
sidecar/send-format.mjs                       2026-07-28
sidecar/stream-staleness.mjs                  2026-07-28
sidecar/patch-spectrum-mixed-attachments.mjs  2026-06-25
```

`patch-spectrum-mixed-attachments.mjs`(6-25,早于清单)在列;7-28 拆出来的两个不在列。
**一份手写的文件清单,在它所枚举的目录被重构时静默过期** —— 与本项目
`CLAUDE.md` 里「白名单外的锚点连分母都进不去」是同一物种。
可迁移的修法:清单改为**从 `index.mjs` 的 import 图推导**,或镜像整个目录再排除
`node_modules`(声明要排除什么,而不是枚举要包含什么)。

### 7.2 ■ `H-R11F-C-b` —— Home Assistant 是片内唯一「截断不出声」的适配器

`plugins/platforms/homeassistant/adapter.py:431` 把出站内容硬切到 4096
(§6 块三),**不记日志、不加省略号、不加脚注**,随后返回成功 —— 调用方无从得知内容被截过。

`plugins/platforms/homeassistant/adapter.py:442 @ 863e313`

```
                    if resp.status < 300:
                        return SendResult(success=True, message_id=uuid.uuid4().hex[:12])
```

片内全部硬切片位置(14 家逐个扫,不抽样):

```verify
grep -rn "\[: *self\.MAX_MESSAGE_LENGTH\]\|\[: *MAX_MESSAGE_LENGTH\]" /home/user/hermes-agent/plugins/platforms/{photon,a2a,whatsapp,line,buzz,teams,simplex,mattermost,email,irc,raft,ntfy,homeassistant,sms}/adapter.py | sed "s|.*/plugins/|plugins/|"
```

```text
plugins/platforms/photon/adapter.py:2448:            text[: self.MAX_MESSAGE_LENGTH],
plugins/platforms/photon/adapter.py:2489:            text = text[: self.MAX_MESSAGE_LENGTH]
plugins/platforms/photon/adapter.py:2528:            "title": title.strip()[: self.MAX_MESSAGE_LENGTH],
plugins/platforms/ntfy/adapter.py:146:    return message[:MAX_MESSAGE_LENGTH].encode("utf-8")
plugins/platforms/ntfy/adapter.py:434:        body = content[:self.MAX_MESSAGE_LENGTH]
plugins/platforms/homeassistant/adapter.py:431:            "message": content[:self.MAX_MESSAGE_LENGTH],
```

三家有硬切片:photon(3 处)、ntfy(2 处)、homeassistant(1 处)。
**photon 与 ntfy 都先记 warning 再切**(ntfy 见 §6 块四;
photon 见下),**只有 homeassistant 不出声**。

`plugins/platforms/photon/adapter.py:2484 @ 863e313`

```
        if len(text) > self.MAX_MESSAGE_LENGTH:
            logger.warning(
                "[photon] truncating outbound from %d to %d chars",
                len(text), self.MAX_MESSAGE_LENGTH,
            )
            text = text[: self.MAX_MESSAGE_LENGTH]
```

ntfy 甚至专门抽了个 `_truncate_body()` 助手,docstring 明写是为了让
"adapter 与 standalone 两处截断能在日志里区分开":

`plugins/platforms/ntfy/adapter.py:135 @ 863e313`

```
def _truncate_body(message: str, *, context: str) -> bytes:
    """Apply the ntfy 4096-char limit, logging a warning on truncation.

    ``context`` is included in the log message so adapter and standalone
    truncations can be told apart in logs.
    """
```

**同一目录树里已经立好的约定,homeassistant 是唯一的例外。**

**可达性(说清楚,不夸大)**:正常流式路径下已先预切块,每块 ≤3996 < 4096,**这一刀切不到**。

`gateway/stream_consumer.py:1458 @ 863e313`

```
        safe_limit = max(500, raw_limit - 100)
        chunks = self._split_text_chunks(continuation, safe_limit, len_fn=_len_fn)
```

但 `_send_with_retry` 把 `content` **原样**转给 `self.send()`,不做任何切块,
非流式调用方因此能把超长内容送到这一刀上。

`gateway/platforms/base.py:5060 @ 863e313`

```
        result = await self.send(
            chat_id=chat_id,
            content=content,
            reply_to=reply_to,
            metadata=metadata,
        )
```
**所以这是一条"第二道防线设计成了静默丢数据"**,而不是"每次都丢"。

**同一插件的两条发送路径对这个上限的处理还不一致**:
`register()` 同时注册了 `standalone_sender_fn=_standalone_send`
(供网关不在本进程时的 cron 投递),而它**完全不设上限**:

`plugins/platforms/homeassistant/adapter.py:529 @ 863e313`

```
    payload = {"message": message, "target": chat_id}
```

同一个平台、同一个 `register()` 声明的 `max_message_length`,
**进程内切到 4096、进程外一刀不切**。

**◇ 附带**:`website/docs/user-guide/messaging/homeassistant.md` 全文不含
`4096` / `truncat` / `length` / `limit` / `chunk` / `split` 任一词(grep 零命中),
所以这个上限**在用户文档里完全不存在**。

### 7.3 ▲(码内)`H-R11F-C-c` —— 「HA 事件是系统生成的」这句注释与相邻代码不符

`gateway/authz_mixin.py:398` 的注释(§6 块五)给无条件放行给的理由是
**"HA events are system-generated (state changes), not user-initiated messages"**。

但同一条链上,事件正文是由**实体属性**拼出来的:

`plugins/platforms/homeassistant/adapter.py:363 @ 863e313`

```
        friendly_name = new_state.get("attributes", {}).get("friendly_name", entity_id)
```

`friendly_name` 是 HA 里**可被用户/集成任意设定**的显示名,它连同状态值一起进入
`MessageEvent.text`,再送进 agent 回合 ——

`plugins/platforms/homeassistant/adapter.py:344 @ 863e313`

```
        await self.handle_message(msg_event)
```

所以"system-generated"
描述的是**触发时机**(不是人打字触发的),而不是**内容来源**;
把它当作"内容可信"的理由,是这条注释与代码的落差。

**记为 ▲(码内)而不是地图级 ▲**:这是代码注释,不是 README/AGENTS.md/website/docs。
**用户文档侧反而是准确的**,原文如下。

`website/docs/user-guide/messaging/homeassistant.md:188 @ 863e313`

> - **Authorization** — HA events are always authorized (no user allowlist needed, since the `HASS_TOKEN` authenticates the connection)

字面为真,故**不是 ▲**。

**缓解事实要一并说**:默认是**关着**的 —— 没配 watch 过滤器时事件全部丢弃:

`plugins/platforms/homeassistant/adapter.py:308 @ 863e313`

```
        elif not self._watch_all:
            # No filters configured and watch_all is off — drop the event
            return
```

### 7.4 ◇ `H-R11F-C-d` —— `kind: platform` 挡不住全生命周期钩子

raft 的 `plugin.yaml` 声明 `kind: platform`,而它在 `register()` 里注册了
**7 个会话/LLM/工具生命周期钩子**(`plugins/platforms/raft/adapter.py:846`–`:852`,
见 §4.5 表)。而**捆绑的 platform 插件是自动加载的**(理由:开箱即用)——

`hermes_cli/plugins.py:1468 @ 863e313`

```
            if manifest.source == "bundled" and manifest.kind == "platform":
                self._register_deferred_platform(manifest)
                continue
```

于是一个自动加载的"平台"插件同时获得了
`pre_llm_call` / `pre_tool_call` / `post_tool_call` 的观察位。
`plugin.yaml` 的 `kind` **不是权限声明,只是加载路由的分类**。
文档未就此表态,故记 ◇ 而非 ■。

---

## 8. 已知线索复核(独立复核,不照抄)

### 8.1 `H-R9D-D-b`(QQBot 无插件 / 无 `max_message_length` / 静默切断仍返回 success）

**QQBot 不在本片范围内,而且不在 `plugins/platforms/` 下。**
`plugins/platforms/` 恰好 22 个平台目录(片 A 3 家 + 片 B 5 家 + 片 C 14 家 = 22),
其中没有 qqbot;QQBot 位于 `gateway/platforms/qqbot/`,是**核心内置平台**而非插件。

**搜索面(三条,逐条给出)**:(a) `plugins/platforms/` 下的目录总数;
(b) 全仓名为 `qqbot` 的目录(排除 `node_modules`);(c) 任何路径含 `qqbot` 的
`plugin.yaml` 数量。

```verify
ls -d /home/user/hermes-agent/plugins/platforms/*/ | wc -l; find /home/user/hermes-agent -type d -name qqbot -not -path "*/node_modules/*" | sed "s|/home/user/hermes-agent/||"; find /home/user/hermes-agent -path "*qqbot*" -name "plugin.yaml" | wc -l
```

```text
22
gateway/platforms/qqbot
0
```

故"QQBot 无插件"**属实**(它没有 manifest,不走插件加载器),
但其余两半(无 `max_message_length`、静默切断)落在 `gateway/` 而非 `plugins/`,
**本片不据此下结论**。

**但同型形态在本片内存在,且已独立取证**:
(a) `max_message_length` 未传的有 a2a / buzz / raft 三家(§4.3 矩阵),
它们同时也没设类属性 `MAX_MESSAGE_LENGTH`,于是两处都吃 4096 兜底
(`gateway/platforms/base.py:2870`)—— **不是"无上限",是"默认上限"**,不构成静默切断;
(b) 真正的"静默切断 + `success=True`"形态在 **homeassistant**,已另铸为 `H-R11F-C-b`。

### 8.2 `H-R9D-D-f`(配了 `HASS_TOKEN` 即自动启用且无逐次审批)

**两半都属实,且各有独立锚点。**

**自动启用**:

`gateway/config.py:2081 @ 863e313`

```
    hass_token = getenv("HASS_TOKEN")
    if hass_token:
        if Platform.HOMEASSISTANT not in config.platforms:
            config.platforms[Platform.HOMEASSISTANT] = PlatformConfig()
        config.platforms[Platform.HOMEASSISTANT].enabled = True
        config.platforms[Platform.HOMEASSISTANT].token = hass_token
```

**无逐次审批**,三条互相独立的结构性证据:

1. `gateway/authz_mixin.py:403` 对 `Platform.HOMEASSISTANT` 直接 `return True`(§6 块五);
2. homeassistant 的 `register()` **不传** `allowed_users_env` / `allow_all_env`
   —— 全片仅它与 raft 两家如此(§4.3 矩阵),即**核心侧根本没有可查的名单变量名**;
3. `plugins/platforms/homeassistant/adapter.py` 全文无 `allowed_users` / `allow_all` /
   `_is_sender_authorized` / `enforces_own_access_policy` 任一符号(grep 零命中),
   即**插件侧也没有自建的访问控制**。

**一处需要修正上一轮口径的地方**:这不是"未文档化的默认放行"——
`website/docs/user-guide/messaging/homeassistant.md:188` 把它**明写为设计**(§7.3 引文)。
故它是一条**被记录在案的信任决策**,该讨论的是这个决策是否成立(§7.3 的 ▲(码内)),
而不是"文档没说"。

---

## 9. 判据 1–5 是否适用于插件形态(派工书要求的验收项)

五条判据在平台插件上**全部适用,无需降低**,但有一条要补充:

**建议补第 6 条「反向接缝」**:判据 2 说的是"每个对外接缝逐项列全",默认方向是
**插件暴露给宿主**什么。但本片最有价值的两个发现(§7.1 的镜像清单、
§4.8 的 38 个"声明了但插件不读"的 env)都在**反方向**:
**宿主按约定去插件那里取/替插件做**的事。这类接缝没有函数签名、没有 ABC,
只有命名约定与手写清单,因此**最容易过期**。建议后续轮次在判据 2 里明写
"双向枚举:插件→宿主 的注册面,与 宿主→插件 的约定面"。

---

## 10. 移交项

| 案号 | 现象与锚点 | 去向建议 |
|---|---|---|
| `H-R11F-C-a` | photon 镜像清单漏两个自身 import 的模块。`plugins/platforms/photon/sidecar_paths.py:51`:`_MIRROR_FILES = (` 只列 4 项,而 `plugins/platforms/photon/sidecar/index.mjs:69`:`import { chooseSendFormat } from "./send-format.mjs";` 需要第 5 项 | R12 装订进"插件/sidecar 文件布局"一节;可作"枚举式清单 vs 排除式声明"的范例 |
| `H-R11F-C-b` | homeassistant 是片内唯一静默截断者。`plugins/platforms/homeassistant/adapter.py:431`:`"message": content[:self.MAX_MESSAGE_LENGTH],` 无日志;对照 `plugins/platforms/ntfy/adapter.py:434`:`body = content[:self.MAX_MESSAGE_LENGTH]` 前有 warning | 与片 A/B 的同类截断点合并,做一张全 22 家的"截断是否出声"表 |
| `H-R11F-C-c` | 注释称 HA 事件是系统生成故可信,但正文含实体属性。`gateway/authz_mixin.py:400`:`# connection, so HA events are always authorized.` 对 `plugins/platforms/homeassistant/adapter.py:363`:`friendly_name = new_state.get("attributes", {}).get("friendly_name", entity_id)` | ▲(码内)计数;与 webhook 分支(同一行放行)一并复核 |
| `H-R11F-C-d` | `kind: platform` 不限制能力面。`plugins/platforms/raft/adapter.py:846`:`ctx.register_hook("on_session_start", _on_session_start)` 出现在一个 `kind: platform` 插件里 | 交片 F(插件公共面)与 D 合并判定:`kind` 到底约束什么 |
| `H-R11F-C-e` | 两个同名不同物的长度声明无人核对。注册面 `gateway/platform_registry.py:94`:`max_message_length: int = 0` 与运行期类属性 `plugins/platforms/ntfy/adapter.py:183`:`MAX_MESSAGE_LENGTH = MAX_MESSAGE_LENGTH` | 建议后续轮次加一条机械核对(11/14 传了注册面值,6/14 设了类属性,交集未验证) |

---

## 11. 数据产物

- `data/r11f/c/env-entries.txt` —— 110 条 env 逐条(平台 / R 或 O / 变量名)
- `data/r11f/c/env-read-only.txt` —— 41 条"读了但没声明"逐条
- `data/r11f/c/register-values.txt` —— 14 家 `register_platform` 实参逐项
- `data/r11f/c/required-env-split.txt` —— `requires_env` vs `required_env` 逐平台
- `data/r11f/c/inherited-untouched.txt` —— 100 个无人覆写的基类成员逐个
- `data/r11f/c/contract-additions.txt` —— 各家新增成员逐个

---

## 完成信号

**片号**:R11F 片 C —— `plugins/platforms/` 长尾 14 家(photon / a2a / whatsapp / line /
buzz / teams / simplex / mattermost / email / irc / raft / ntfy / homeassistant / sms)。

**产出文件**:

- 底稿 `notes/r11f-raw-c-platforms-longtail.md`(本文件)
- 探针 6 支:`data/r11f/probes/c_rollcall.py`、`c_adapter_contract.py`、
  `c_manifest_seam.py`、`c_register_seam.py`、`c_env_seam.py`、`c_required_env_split.py`
- 数据 6 份:`data/r11f/c/{env-entries,env-read-only,register-values,required-env-split,inherited-untouched,contract-additions}.txt`

**五条判据**:

| # | 判据 | 达成情况 |
|---|---|---|
| 1 | 点名到位 | **达成**。59/59 全路径 + 一句话角色(§2);两组同型薄文件归组叙述但组内逐个列全路径;§2.2 末的自检 verify 块把 `slices/C.txt` 的 59 条路径逐条回查本文件,`named_in_note=59  MISSING=0` |
| 2 | 接缝穷举 | **达成**。六个接缝面逐项列全、无抽样(§4),枚举命令与条数见下 |
| 3 | 端到端链 | **达成**。ntfy 一次完整往返 16 跳,逐跳带锚点(§5) |
| 4 | 逐字取证 | **达成**。全文 **33** 个逐字源码围栏块(§6 集中给出块一至块五,其余散在 §4/§7/§8);`verify_citations.py` 报 `citations=47 OK=34`,**零 MISMATCH / 零 BLOCK-DRIFT** |
| 5 | 记号 | **达成**。■×2(`H-R11F-C-a`/`-b`)、▲(码内)×1(`-c`)、◇×1(`-d`);地图级 ▲ **0 条** |

**点名文件数**:**59**(= `c_rollcall.py --counts` 的 `files=59`,25,334 行,14 平台)。

**关卡读数(两道都跑到退出码 0)**:

- `verify_citations.py`:`citations=47  OK=34  UNCHECKED=13`,**可校验比例 72.3%**(≥70% 下限);
  `table_anchors=24  OK=24`(表格锚点声明率单独报,不并入可校验比例);
  `OK: every code-block-backed citation matches the baseline`
- `verify_evidence_commands.py`:`paired=23  unpaired=0  differing=0  timedout=0`;
  输出 `OK: every paired verify command reproduces its pasted output`

**接缝枚举命令与条数**:

| 接缝 | 枚举命令 | 条数 |
|---|---|---|
| `plugin.yaml` 顶层键 | `c_manifest_seam.py --keymatrix` | 8 键 × 14 份 = **112 格**;不同键 8 个,无人读的 0 个 |
| `requires_env`/`optional_env` | `c_manifest_seam.py --env` / `--envfields` | **110 条**变量(25 required + 85 optional),子字段 **6 种** |
| 注册面 `PlatformEntry` | `c_register_seam.py --matrix` | 22 字段 × 14 家 = **308 格**,实传 **232**,插件不得填 **2** |
| 适配器契约面 | `c_adapter_contract.py --abstract` / `--overridden` / `--inherited` | 基类 **126** 成员 = 抽象 **4**(56 格全满)+ 被覆写可选 **22**(308 格)+ 无人碰 **100**;各家新增 **205** |
| `ctx.*` 注册调用 | AST(见 §4.5) | **4 种**:`register_platform` 14 处、`register_hook` 7 处、`register_tool` 1 处(循环注册 5 个工具)、`register_cli_command` 1 处 |
| env 声明 vs 读取 | `c_env_seam.py --counts` | 声明 **110**、字面量读取 **113**、仅声明 **38**、仅读取 **41**、动态读取 **16** |
| 两处 required 声明一致性 | `c_required_env_split.py --counts` | 14 家 **14 一致 / 0 不一致** |
| photon sidecar 本地路由 | grep(见 §3 形态 D) | **12** 条 |

**新铸记号编号**:`H-R11F-C-a`(■ sidecar 镜像清单过期)、
`H-R11F-C-b`(■ homeassistant 静默截断 + 两条发送路径上限不一致)、
`H-R11F-C-c`(▲(码内)authz 注释与事件内容来源不符)、
`H-R11F-C-d`(◇ `kind: platform` 不约束能力面)、
`H-R11F-C-e`(移交:两个同名不同物的长度声明无人核对)。

**硬边界自查**:基线 `git status --porcelain` 为空;全部执行基线相关的命令带
`HERMES_DISABLE_LAZY_INSTALLS=1`;探针为纯 AST/YAML 解析,**未 import 基线模块**;
未改 `scripts/`、`chapters/`、台账、`CLAUDE.md`;未扩充 venv;
未触碰 `data/inflight/*.claim`;只写了 claim 声明的三条路径。
