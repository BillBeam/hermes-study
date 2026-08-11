# R11F 片 E 底稿 —— 媒体 / 会议 / 浏览器型插件(L2 结构级)

> **范围**:`plugins/{google_meet, image_gen, video_gen, spotify, browser}`,50 文件 / 10,643 行。
> **基线**:`/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`,只读。
> **溯源约定**:凡对基线行为的断言,锚点写作 `路径:行号 @ 863e313`,单独成行、置于代码块之前;
> 围栏块是逐字源码摘录,`text` / `verify` 围栏是声明式非源码。
> **深度**:L2 = 读接口面而不读实现体 —— **可以不读实现,但不能抽样接口**。

---

## 0. 这一片是什么形态

五个插件目录,**两种截然不同的形态**:

| 形态 | 目录 | 共同点 |
|---|---|---|
| **多后端池**(provider pool) | `image_gen/`(7 目录)、`video_gen/`(3 目录)、`browser/`(3 目录) | 一个**能力**(生图 / 生视频 / 云浏览器),多个第三方**后端**并存;每个后端实现同一个 ABC,注册进一个进程内注册表;真正跑哪一个由 `config.yaml` 的一个键选出来 |
| **单体服务接入** | `google_meet/`(17 文件)、`spotify/`(4 文件) | 没有后端池;插件直接注册**工具**(tool),把一个外部服务(Google Meet / Spotify Web API)接进 agent 的工具面 |

这两种形态的**接缝位置完全不同**:多后端池的接缝在「provider 注册 + 选择」这一层,
单体服务的接缝在「工具注册 + 凭据」这一层。google_meet 又比 spotify 多出三个自己的接缝
(CLI 子命令树、进程/文件 IPC、远程 node 的 WebSocket RPC)。本底稿按接缝而不是按目录组织。

**术语锚定**(首次出现):
- **provider(后端)** —— 一个能力域下可替换的第三方实现。本片三个能力域各有自己的 ABC。
- **ABC**(abstract base class,抽象基类)—— Python 里用 `abc.abstractmethod` 标出「子类必须实现」的方法的基类。
- **manifest / `plugin.yaml`** —— 每个插件目录里的清单文件,声明名字、种类、需要哪些环境变量。
- **CDP**(Chrome DevTools Protocol)—— Chrome 的远程调试协议;云浏览器返回一个 `cdp_url`,本地驱动连上去操控远端浏览器。
- **PKCE OAuth** —— OAuth 授权码流程的一个变体,不需要在客户端保存 client secret,适合命令行工具。

---

## 1. 判据 1 · 点名表(50 个文件逐个)

同型薄文件按组叙述,**组内仍逐个列全路径**。分组的文件数与行数不靠手算,由派工清单复算:

```verify
cd /home/user/hermes-study && awk -F'\t' '{d=$1; sub(/\/[^/]*$/,"",d); if(d ~ /^plugins\/image_gen/) g="image_gen"; else if (d ~ /^plugins\/video_gen/) g="video_gen"; else if (d ~ /^plugins\/browser/) g="browser"; else if (d ~ /^plugins\/spotify/) g="spotify"; else g="google_meet"; n[g]++; l[g]+=$2; N++; L+=$2} END{for(k in n) printf "%-12s %2d files %6d lines\n", k, n[k], l[k]; printf "%-12s %2d files %6d lines\n", "TOTAL", N, L}' data/r11f/slices/E.txt | sort
```

```text
TOTAL        50 files  10643 lines
browser       9 files    864 lines
google_meet  17 files   3735 lines
image_gen    14 files   3416 lines
spotify       4 files    968 lines
video_gen     6 files   1660 lines
```

### 1.1 `plugins/image_gen/` —— 7 目录 / 14 文件 / 3,416 行

每个目录同一形状:`__init__.py` 里既定义 provider 类、又定义 `register(ctx)` 入口;
`plugin.yaml` 只声明身份与所需 env。

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/image_gen/deepinfra/__init__.py` | 336 | DeepInfra 后端。**唯一全动态模型发现**的生图后端 —— 模型目录从 `api.deepinfra.com` 的 tagged catalog 现拉,文件里没有硬编码模型 id |
| `plugins/image_gen/deepinfra/plugin.yaml` | 7 | 清单;`requires_env: [DEEPINFRA_API_KEY]` |
| `plugins/image_gen/fal/__init__.py` | 211 | FAL.ai 后端。**最薄的一个** —— 真正的目录/载荷/托管网关逻辑全在 `tools/image_generation_tool.py`,本文件用「调用时再 import」的间接层回跳过去 |
| `plugins/image_gen/fal/plugin.yaml` | 7 | 清单;`requires_env: [FAL_KEY]` |
| `plugins/image_gen/krea/__init__.py` | 744 | Krea 后端。**唯一异步作业型** —— 提交返回 `job_id`,内部轮询 `GET /jobs/{id}` 后把同步 `generate()` 契约兑现出来;支持 Nous 订阅托管网关 |
| `plugins/image_gen/krea/plugin.yaml` | 7 | 清单;`requires_env: [KREA_API_KEY]` |
| `plugins/image_gen/openai/__init__.py` | 419 | OpenAI `gpt-image-2` 后端;把 low/medium/high 三档质量做成三个**虚拟模型 id** |
| `plugins/image_gen/openai/plugin.yaml` | 7 | 清单;`requires_env: [OPENAI_API_KEY]` |
| `plugins/image_gen/openai-codex/__init__.py` | 639 | 同一个 `gpt-image-2`,但走 **ChatGPT/Codex OAuth** + Responses API 的 `image_generation` 工具,而不是 `images.generate` REST |
| `plugins/image_gen/openai-codex/plugin.yaml` | 5 | 清单;**全片唯一没有 `requires_env` 也没有 `provides_*` 的清单**(凭据来自 OAuth,不是 env) |
| `plugins/image_gen/openrouter/__init__.py` | 526 | OpenRouter 兼容后端。**一个目录注册两个 provider**(`openrouter` 与 `nous`),两者只差 runtime 名与配置命名空间 |
| `plugins/image_gen/openrouter/plugin.yaml` | 7 | 清单;`requires_env: [OPENROUTER_API_KEY]` |
| `plugins/image_gen/xai/__init__.py` | 494 | xAI `grok-imagine-image` 后端;文生图走 `/images/generations`,改图走 `/images/edits`(改图强制换成 `-quality` 模型) |
| `plugins/image_gen/xai/plugin.yaml` | 7 | 清单;`requires_env: [XAI_API_KEY]` |

### 1.2 `plugins/video_gen/` —— 3 目录 / 6 文件 / 1,660 行

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/video_gen/deepinfra/__init__.py` | 90 | DeepInfra 生视频后端。**全片最薄的 provider(90 行)** —— 它继承 `OpenAICompatibleVideoGenProvider` 复用整套 SDK 管线,自己只声明身份、凭据变量名、模型发现 |
| `plugins/video_gen/deepinfra/plugin.yaml` | 7 | 清单;`requires_env: [DEEPINFRA_API_KEY]` |
| `plugins/video_gen/fal/__init__.py` | 624 | FAL 生视频后端。用户选的是**模型家族**(Veo 3.1 / Kling / Pixverse…),插件按有没有 `image_url` 自动在该家族的 t2v / i2v 端点之间路由 |
| `plugins/video_gen/fal/plugin.yaml` | 7 | 清单;`requires_env: [FAL_KEY]` |
| `plugins/video_gen/xai/__init__.py` | 925 | xAI Grok Imagine 生视频后端。**片内最大的单个 provider** —— 文生视频 / 图生视频 / 参考图生视频 / 视频编辑 / 视频续接 / xAI 存储公开链接 |
| `plugins/video_gen/xai/plugin.yaml` | 7 | 清单;`requires_env: [XAI_API_KEY]` |

### 1.3 `plugins/browser/` —— 3 目录 / 9 文件 / 864 行

这一组是全仓**分层最干净的插件形态**:`provider.py` 放类,`__init__.py` 只做实例化+注册,`plugin.yaml` 只做声明。

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/browser/browser_use/__init__.py` | 14 | 注册入口:`register(ctx)` → `ctx.register_browser_provider(BrowserUseBrowserProvider())` |
| `plugins/browser/browser_use/provider.py` | 324 | Browser Use 后端。**唯一双路认证** —— 直连 `BROWSER_USE_API_KEY`,或走 Nous 托管网关按订阅计费;托管模式下带 `X-Idempotency-Key` 防重复建会话 |
| `plugins/browser/browser_use/plugin.yaml` | 7 | 清单;`provides_browser_providers: [browser-use]` |
| `plugins/browser/browserbase/__init__.py` | 15 | 注册入口 |
| `plugins/browser/browserbase/provider.py` | 300 | Browserbase 后端。**唯一有付费特性降级** —— stealth / proxies / keep-alive 由四个 env 开关控制,付费特性不可用时自动回落再建一次会话 |
| `plugins/browser/browserbase/plugin.yaml` | 7 | 清单;`provides_browser_providers: [browserbase]` |
| `plugins/browser/firecrawl/__init__.py` | 16 | 注册入口 |
| `plugins/browser/firecrawl/provider.py` | 174 | Firecrawl 云浏览器后端(`/v2/browser`)。**与 `plugins/web/firecrawl/` 共用同一个 API key、打不同端点**;正因如此它被**排除在自动探测之外** |
| `plugins/browser/firecrawl/plugin.yaml` | 7 | 清单;`provides_browser_providers: [firecrawl]` |

### 1.4 `plugins/spotify/` —— 4 文件 / 968 行

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/spotify/__init__.py` | 66 | 注册 7 个工具进 `spotify` toolset;每个工具挂同一个 `check_fn`,未登录时工具**仍注册**(所以 `hermes tools` 里看得见)但运行期拒绝派发 |
| `plugins/spotify/client.py` | 435 | Spotify Web API 的薄客户端(httpx)。凭据与 base_url 全部来自 `hermes_cli/auth.py` 的 `resolve_spotify_runtime_credentials()`,插件自己不持有任何 URL 或 env 名 |
| `plugins/spotify/tools.py` | 454 | 7 个工具的 schema + handler + 参数归一化(`normalize_spotify_id` / `_uri` / `_uris`) |
| `plugins/spotify/plugin.yaml` | 13 | 清单;`provides_tools` 列全 7 个工具名 |

### 1.5 `plugins/google_meet/` —— 17 文件 / 3,735 行

形态与其余四组都不同:它不是 provider 池,而是**「把一个带 GUI 的第三方会议接进 agent」**。
因此它是全片唯一同时具备「子进程生命周期管理 + 文件 IPC + 独立 CLI 子命令树 + 跨机 RPC」的插件。

**顶层(6 文件 / 2,376 行)**

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/google_meet/__init__.py` | 103 | 插件入口。注册 5 个 `meet_*` 工具、1 个 CLI 命令、1 个 `on_session_end` 钩子;**在 `register()` 里做操作系统门禁**,非 linux/darwin 直接不注册 |
| `plugins/google_meet/tools.py` | 348 | 5 个工具的 schema + handler。每个 handler 都有「本地 / 远程 node」两条分支 |
| `plugins/google_meet/cli.py` | 476 | `hermes meet <子命令>` 的参数树与实现(setup / install / auth / join / status / transcript / say / stop / node) |
| `plugins/google_meet/process_manager.py` | 339 | 子进程生命周期管理器。**同时只允许一场会议**;活动状态写在 `$HERMES_HOME/workspace/meetings/.active.json` |
| `plugins/google_meet/meet_bot.py` | 862 | 真正的 bot 进程本体(Playwright 无头 Chromium + 实时字幕 DOM 抓取)。**作为独立子进程运行**,只通过文件与主进程通信 |
| `plugins/google_meet/audio_bridge.py` | 248 | v2 虚拟音频桥。Linux 用 `pactl` 造 null-sink + virtual source 喂给 Chrome 的假麦克风;macOS 只检测 BlackHole 是否装了;Windows 不支持 |

**realtime 子包(2 文件 / 342 行)**

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/google_meet/realtime/__init__.py` | 10 | 只做 re-export:`RealtimeSession`、`RealtimeSpeaker` |
| `plugins/google_meet/realtime/openai_client.py` | 332 | OpenAI Realtime API 的同步 WebSocket 客户端 + 文件队列朗读器:文本 → 音频增量 → 追加 PCM 字节到文件,由音频桥消费 |

**node 子包(6 文件 / 722 行)** —— v3 的「远程 node 主机」:让 bot 跑在用户的 Mac 上、gateway 跑在 Linux 服务器上

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/google_meet/node/__init__.py` | 54 | 子包说明 + 公共面 re-export(`NodeClient` / `NodeServer` / `NodeRegistry` / 协议函数) |
| `plugins/google_meet/node/protocol.py` | 124 | JSON-over-WebSocket 的信封格式与校验:请求 / 响应 / 错误三种信封,6 种合法请求类型,共享 bearer token 校验 |
| `plugins/google_meet/node/client.py` | 107 | gateway 侧 RPC 客户端。**每次调用开一条短命同步 WS,发一个请求收一个响应就关** —— 这样非 async 的工具 handler 也能直接用 |
| `plugins/google_meet/node/server.py` | 200 | node 侧服务端。首次启动铸 32 位十六进制 token 持久化到 `node_token.json`(权限 0600),把 RPC 分派给本机的 `process_manager` |
| `plugins/google_meet/node/registry.py` | 112 | gateway 侧已批准 node 的本地 JSON 名册(`$HERMES_HOME/workspace/meetings/nodes.json`),把名字解析成 `(url, token)` |
| `plugins/google_meet/node/cli.py` | 125 | `hermes meet node <run/list/approve/remove/status/ping>` 子命令树 |

**文档与清单(3 文件 / 295 行)**

| 文件 | 行 | 角色 |
|---|---:|---|
| `plugins/google_meet/plugin.yaml` | 16 | 清单。**片内键最多的一份**(8 个顶层键) |
| `plugins/google_meet/README.md` | 131 | 面向用户的安装与使用说明(v1/v2/v3 三阶段) |
| `plugins/google_meet/SKILL.md` | 148 | 面向**模型**的技能卡:什么时候该用 `meet_*` 工具、怎么组合、边界是什么 |

**点名合计:14 + 6 + 9 + 4 + 17 = 50 文件。**

---

## 2. 判据 2 · 接缝穷举(本片重心)

下面九个接缝,**每个都逐项列全、不抽样**,并给机械枚举命令与条数。

### 2.1 接缝 A —— `plugin.yaml` 清单键面(15 份逐份列全)

片内 15 份 manifest,合计只用了 **10 个不同顶层键**。全表见
`data/r11f/e/manifest-census.txt`,枚举命令与摘要:

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/e_manifest_census.py 2>/dev/null | tail -14
```

```text
    requires_env=[XAI_API_KEY]

manifests: 15   distinct top-level keys: 10
  READ   author                       x15
  READ   description                  x15
  UNREAD hooks                        x1
  READ   kind                         x15
  READ   name                         x15
  UNREAD platforms                    x1
  UNREAD provides_browser_providers   x3
  READ   provides_tools               x2
  READ   requires_env                 x9
  READ   version                      x15
UNREAD keys in slice E: 3 -> hooks, platforms, provides_browser_providers
```

**逐份键集**(顺序即文件内顺序):

| manifest | 顶层键 | `requires_env` / `provides_*` 逐条 |
|---|---|---|
| `plugins/browser/browser_use/plugin.yaml` | name, version, description, author, kind, provides_browser_providers | `provides_browser_providers: [browser-use]` |
| `plugins/browser/browserbase/plugin.yaml` | 同上 | `provides_browser_providers: [browserbase]` |
| `plugins/browser/firecrawl/plugin.yaml` | 同上 | `provides_browser_providers: [firecrawl]` |
| `plugins/google_meet/plugin.yaml` | name, version, description, author, kind, **platforms**, provides_tools, **hooks** | `platforms: [linux, macos]`;`provides_tools: [meet_join, meet_leave, meet_status, meet_transcript, meet_say]`;`hooks: [on_session_end]` |
| `plugins/image_gen/deepinfra/plugin.yaml` | name, version, description, author, kind, requires_env | `requires_env: [DEEPINFRA_API_KEY]` |
| `plugins/image_gen/fal/plugin.yaml` | 同上 | `requires_env: [FAL_KEY]` |
| `plugins/image_gen/krea/plugin.yaml` | 同上 | `requires_env: [KREA_API_KEY]` |
| `plugins/image_gen/openai/plugin.yaml` | 同上 | `requires_env: [OPENAI_API_KEY]` |
| `plugins/image_gen/openai-codex/plugin.yaml` | name, version, description, author, kind | (无) |
| `plugins/image_gen/openrouter/plugin.yaml` | name, version, description, author, kind, requires_env | `requires_env: [OPENROUTER_API_KEY]` |
| `plugins/image_gen/xai/plugin.yaml` | 同上 | `requires_env: [XAI_API_KEY]` |
| `plugins/spotify/plugin.yaml` | name, version, description, author, kind, provides_tools | `provides_tools: [spotify_playback, spotify_devices, spotify_queue, spotify_search, spotify_playlists, spotify_albums, spotify_library]` |
| `plugins/video_gen/deepinfra/plugin.yaml` | name, version, description, author, kind, requires_env | `requires_env: [DEEPINFRA_API_KEY]` |
| `plugins/video_gen/fal/plugin.yaml` | 同上 | `requires_env: [FAL_KEY]` |
| `plugins/video_gen/xai/plugin.yaml` | 同上 | `requires_env: [XAI_API_KEY]` |

**`optional_env` / `pip_dependencies` / `label` / `external_dependencies` / `provides_web_providers` 在片内 0 份使用。**
(搜索面:上表 15 份 manifest 的全部顶层键,由 `data/r11f/probes/e_manifest_census.py` 的
`top_keys()` 逐行解析,不是 grep 关键字。)

**「谁读这些键」的判定不靠印象**:探针从 `hermes_cli/plugins.py::_parse_manifest` 的函数体里
AST 抽出所有 `data.get("<字面量>")`,得到读取面 = 8 个键。

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
                source=source,
                path=str(plugin_dir),
                kind=kind,
                key=key,
            )
```

于是片内三个键 **`provides_browser_providers`(3 份)、`platforms`(1 份)、`hooks`(1 份)
从来没有被加载器读过** —— 它们是纯声明,注册与门禁全在代码里做(见 2.2 与 2.9)。
这条通向本片的两条 ■,见 §5。

### 2.2 接缝 B —— provider / 工具的注册面

**注册入口逐个列全**:片内每个插件目录恰好一个 `register(ctx)`。

```verify
cd /home/user/hermes-agent && grep -rn "^def register(" plugins/browser plugins/google_meet plugins/image_gen plugins/spotify plugins/video_gen --include=*.py | sort
```

```text
plugins/browser/browser_use/__init__.py:12:def register(ctx) -> None:
plugins/browser/browserbase/__init__.py:13:def register(ctx) -> None:
plugins/browser/firecrawl/__init__.py:14:def register(ctx) -> None:
plugins/google_meet/__init__.py:65:def register(ctx) -> None:
plugins/image_gen/deepinfra/__init__.py:334:def register(ctx) -> None:
plugins/image_gen/fal/__init__.py:209:def register(ctx) -> None:
plugins/image_gen/krea/__init__.py:742:def register(ctx) -> None:
plugins/image_gen/openai-codex/__init__.py:637:def register(ctx) -> None:
plugins/image_gen/openai/__init__.py:417:def register(ctx) -> None:
plugins/image_gen/openrouter/__init__.py:523:def register(ctx: Any) -> None:
plugins/image_gen/xai/__init__.py:492:def register(ctx: Any) -> None:
plugins/spotify/__init__.py:56:def register(ctx) -> None:
plugins/video_gen/deepinfra/__init__.py:88:def register(ctx) -> None:
plugins/video_gen/fal/__init__.py:622:def register(ctx) -> None:
plugins/video_gen/xai/__init__.py:923:def register(ctx) -> None:
```

**15 个入口。** 它们通过 `PluginContext` 这个门面只用到 **6 种** 注册方法,共 17 个调用点:

```verify
cd /home/user/hermes-agent && grep -rho "ctx\.register_[a-z_]*" plugins/browser plugins/google_meet plugins/image_gen plugins/spotify plugins/video_gen --include=*.py | sort | uniq -c | sort -rn
```

```text
      7 ctx.register_image_gen_provider
      3 ctx.register_video_gen_provider
      3 ctx.register_browser_provider
      2 ctx.register_tool
      1 ctx.register_hook
      1 ctx.register_cli_command
```

**注意「调用点数」不等于「注册出来的东西数」**,两处不对齐都要交代:

1. `ctx.register_tool` 只有 2 个调用点,但它们都在 `for` 循环里 —— google_meet 5 个工具、
   spotify 7 个工具,合计 **12 个工具**。
2. `ctx.register_image_gen_provider` 有 7 个调用点(7 个目录),但注册出来的是 **8 个** provider ——
   openrouter 那个 `register()` 遍历 `_build_providers()` 返回的两个实例:

`plugins/image_gen/openrouter/__init__.py:523 @ 863e313`

```
def register(ctx: Any) -> None:
    """Register the OpenRouter + Nous Portal image gen providers."""
    for provider in _build_providers():
        ctx.register_image_gen_provider(provider)
```

所以注册面的**权威读数只能在运行期取**。下面这条把插件真的跑一遍再问三个注册表:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python /home/user/hermes-study/data/r11f/probes/e_registration_surface.py 2>/dev/null
```

```text
lazy-install seal: _allow_lazy_installs() = False
### image_gen: 8 registered
    deepinfra      display='DeepInfra'                class=DeepInfraImageGenProvider @ plugins/image_gen/deepinfra/__init__.py
    fal            display='FAL.ai'                   class=FalImageGenProvider @ plugins/image_gen/fal/__init__.py
    krea           display='Krea'                     class=KreaImageGenProvider @ plugins/image_gen/krea/__init__.py
    nous           display='Nous Portal'              class=OpenRouterCompatImageProvider @ plugins/image_gen/openrouter/__init__.py
    openai         display='OpenAI'                   class=OpenAIImageGenProvider @ plugins/image_gen/openai/__init__.py
    openai-codex   display='OpenAI (Codex auth)'      class=OpenAICodexImageGenProvider @ plugins/image_gen/openai-codex/__init__.py
    openrouter     display='OpenRouter'               class=OpenRouterCompatImageProvider @ plugins/image_gen/openrouter/__init__.py
    xai            display='xAI (Grok)'               class=XAIImageGenProvider @ plugins/image_gen/xai/__init__.py
### video_gen: 3 registered
    deepinfra      display='DeepInfra'                class=DeepInfraVideoGenProvider @ plugins/video_gen/deepinfra/__init__.py
    fal            display='FAL'                      class=FALVideoGenProvider @ plugins/video_gen/fal/__init__.py
    xai            display='xAI'                      class=XAIVideoGenProvider @ plugins/video_gen/xai/__init__.py
### browser: 3 registered
    browser-use    display='Browser Use'              class=BrowserUseBrowserProvider @ plugins/browser/browser_use/provider.py
    browserbase    display='Browserbase'              class=BrowserbaseBrowserProvider @ plugins/browser/browserbase/provider.py
    firecrawl      display='Firecrawl'                class=FirecrawlBrowserProvider @ plugins/browser/firecrawl/provider.py
TOTAL providers registered across the three registries: 14
```

**14 个 provider,来自 13 个目录。**

> **读数是环境的函数,必须一并记环境**(CLAUDE.md 的 R8A 规矩)。上面这条用的是
> `/home/user/hermes-venv`(**87 包**)。同一条命令换成系统 `python3` 得到的是 **13**,
> 少的那一个是 `xai` —— 系统 python3 没有 `httpx`,`plugins/image_gen/xai` 经
> `tools.xai_http` 间接依赖它,于是加载失败、静默少注册一个 provider。
> **两个数都是真的,口径不同**;把哪个写进正文,取决于声明的是哪个环境。

**注册链的三跳**(每一跳都是接缝):

| 跳 | 位置 | 做什么 |
|---|---|---|
| 1 | `plugins/<域>/<名>/__init__.py::register(ctx)` | 实例化 provider,调 `ctx.register_*` |
| 2 | `hermes_cli/plugins.py:670` 的 `register_image_gen_provider` / `:737` 的 `register_video_gen_provider` / `:792` 的 `register_browser_provider` | **类型门禁**:不是对应 ABC 的实例就 WARNING 后忽略,**绝不抛异常**(坏插件不能把宿主搞崩) |
| 3 | `agent/image_gen_registry.py:36` 的 `register_provider` / `agent/video_gen_registry.py:40` 的 `register_provider` / `agent/browser_registry.py:52` 的 `register_provider` | 加锁写进进程内 `dict`;**同名覆盖**并打 debug 日志(为热重载/测试留的语义) |

### 2.3 接缝 C —— provider 契约面(本片最有价值的横向表)

三个能力域各有自己的 ABC,方法面**故意长得像**但并不相同。下表由 AST 生成,
`IMPL` = 实现了抽象方法,`OVR` = 覆写了带默认实现的方法,`-` = 未覆写(用基类默认),
`EXTRA` = 基类没有的新方法(不含双下划线)。

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/e_provider_contract.py 2>/dev/null
```

```text
### image_gen  ABC=ImageGenProvider  (agent/image_gen_provider.py)
methods on ABC: generate*, name*, capabilities, default_model, display_name, get_setup_schema, is_available, list_models   (* = @abstractmethod)
  deepinfra     class=DeepInfraImageGenProvider base=ImageGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)
  fal           class=FalImageGenProvider base=ImageGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)
  krea          class=KreaImageGenProvider base=ImageGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)
  openai        class=OpenAIImageGenProvider base=ImageGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)
  openai-codex  class=OpenAICodexImageGenProvider base=ImageGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)
  openrouter    class=OpenRouterCompatImageProvider base=ImageGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: _resolve_model, _resolve_model_chain, _resolve_runtime
  xai           class=XAIImageGenProvider base=ImageGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=- display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)

### video_gen  ABC=VideoGenProvider  (agent/video_gen_provider.py)
methods on ABC: generate*, name*, capabilities, default_model, display_name, get_setup_schema, is_available, list_models   (* = @abstractmethod)
  deepinfra     class=DeepInfraVideoGenProvider base=OpenAICompatibleVideoGenProvider
    generate=- name=- capabilities=OVR default_model=- display_name=OVR get_setup_schema=OVR is_available=- list_models=OVR
    EXTRA: (none)
  fal           class=FALVideoGenProvider base=VideoGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)
  xai           class=XAIVideoGenProvider base=VideoGenProvider
    generate=IMPL name=IMPL capabilities=OVR default_model=OVR display_name=OVR get_setup_schema=OVR is_available=OVR list_models=OVR
    EXTRA: (none)
  [mixin] OpenAICompatibleVideoGenProvider
    generate=IMPL name=- capabilities=- default_model=- display_name=- get_setup_schema=- is_available=OVR list_models=-
    EXTRA: _api_key, _base_url, _create_and_poll

### browser  ABC=BrowserProvider  (agent/browser_provider.py)
methods on ABC: close_session*, create_session*, emergency_cleanup*, is_available*, name*, display_name, get_setup_schema, is_configured, provider_name   (* = @abstractmethod)
  browser-use   class=BrowserUseBrowserProvider base=BrowserProvider
    close_session=IMPL create_session=IMPL emergency_cleanup=IMPL is_available=IMPL name=IMPL display_name=OVR get_setup_schema=OVR is_configured=- provider_name=-
    EXTRA: _get_config, _get_config_or_none, _headers
  browserbase   class=BrowserbaseBrowserProvider base=BrowserProvider
    close_session=IMPL create_session=IMPL emergency_cleanup=IMPL is_available=IMPL name=IMPL display_name=OVR get_setup_schema=OVR is_configured=- provider_name=-
    EXTRA: _get_config, _get_config_or_none
  firecrawl     class=FirecrawlBrowserProvider base=BrowserProvider
    close_session=IMPL create_session=IMPL emergency_cleanup=IMPL is_available=IMPL name=IMPL display_name=OVR get_setup_schema=OVR is_configured=- provider_name=-
    EXTRA: _api_url, _headers
```

**读这张表要注意的四件事:**

1. **image_gen / video_gen 的方法面完全一致**(8 个方法、其中 2 个抽象),
   而 **browser 的方法面完全不同**(9 个方法、其中 5 个抽象)。
   前两者是「一次调用出一个产物」,只需要 `generate()`;
   browser 是**有生命周期的资源**,所以抽象方法是 `create_session` / `close_session` /
   `emergency_cleanup` 三件套 —— 加上 `is_available` 也被提成抽象(生图那边它有默认实现 `return True`)。
2. **只有 browser 的 ABC 带向后兼容影子方法**:`is_configured()` / `provider_name()`,
   三家实现**一个都没覆写**,全部吃基类的委托。这是 PR #25214 把 in-tree provider 搬进 plugins 时
   为了不改约 6 处调用点留下的。
3. **`video_gen/deepinfra` 是唯一一个不实现任何抽象方法的 provider** —— 它连 `name` 和 `generate` 都没写,
   全部来自 `OpenAICompatibleVideoGenProvider` 这个可复用中间层。这解释了它为什么只有 90 行。
4. **`image_gen/xai` 是唯一不覆写 `default_model()` 的生图 provider**,吃基类默认:

`agent/image_gen_provider.py:136 @ 863e313`

```
    def default_model(self) -> Optional[str]:
        """Return the default model id, or None if not applicable."""
        models = self.list_models()
        if models:
            return models[0].get("id")
        return None
```

**ABC 的 `name` 语义在三个域里不一样**,这是接缝上最容易踩的一处:

`agent/image_gen_provider.py:74 @ 863e313`

```
        """Stable short identifier used in ``image_gen.provider`` config.

        Lowercase, no spaces. Examples: ``fal``, ``openai``, ``replicate``.
        """
```

`agent/browser_provider.py:65 @ 863e313`

```
        """Stable short identifier used in the ``browser.cloud_provider``
        config key.

        Lowercase, hyphens permitted to preserve existing user-visible names.
        Examples: ``browserbase``, ``browser-use``, ``firecrawl``.
        """
```

—— 生图那边写「no spaces」,浏览器那边额外写明「允许连字符」,因为 `browser-use`
这个用户可见名在迁移前就存在,不能为了统一而改。

### 2.4 接缝 D —— provider 选择面(三个域三套规则,**不是一套**)

这是本片最要紧的一处横向对比。三个能力域都有「注册表 + 配置键」,但**选出谁**的规则各不相同:

| 域 | 配置键 | 显式配置但没注册 | 未配置时的兜底 | 兜底是否过滤 `is_available()` |
|---|---|---|---|---|
| image_gen | `image_gen.provider` | 落回自动探测 | ① 只有一个可用 → 用它;② 有 `fal` 且可用 → 用它;③ None | 是 |
| video_gen | `video_gen.provider` | **fail closed,直接 None** | 只有一个可用 → 用它;否则 None | 是 |
| browser | `browser.cloud_provider` | 落回自动探测 | 按固定偏好表走:`browser-use` → `browserbase`;**`firecrawl` 故意不在表里** | 是 |

`agent/browser_registry.py:107 @ 863e313`

```
_LEGACY_PREFERENCE = (
    "browser-use",
    "browserbase",
)
```

**`firecrawl` 被排除在自动探测之外的理由写在代码里,是本片设计取舍里最值得抄走的一条:**

`agent/browser_registry.py:103 @ 863e313`

```
# Matches the pre-migration walk in :func:`tools.browser_tool._get_cloud_provider`.
# Firecrawl is intentionally absent so users with ``FIRECRAWL_API_KEY`` set
# for web-extract don't get silently routed to a paid cloud browser. See
# :func:`_resolve` for the full rationale.
```

即:**一个凭据被两个能力共用时,自动探测必须只认其中一个能力**,
否则用户为 A 付的钱会被 B 悄悄花掉。`FIRECRAWL_API_KEY` 同时是
`plugins/web/firecrawl/`(搜索/抽取)和 `plugins/browser/firecrawl/`(云浏览器)的钥匙。

**另外两条一致的规则**(三个域都这么写):

- **显式配置的 provider 即使 `is_available()` 为假也照样返回** —— 让派发器抛出
  「X_API_KEY is not set」这种精确错误,而不是**静默换后端**。
- **`is_available()` 被包在 try/except 里**(`_is_available_safe`),一个坏插件抛异常不能让整个解析挂掉。

### 2.5 接缝 E —— 凭据面(env 变量逐条列全)

```verify
cd /home/user/hermes-study && HERMES_DISABLE_LAZY_INSTALLS=1 python3 data/r11f/probes/e_credential_egress.py 2>/dev/null | tail -2
```

```text
TOTAL distinct env-shaped literals: 40
TOTAL distinct hosts: 23
```

**这两个数是探针的粗口径读数,必须说清它包含什么**:探针把「全大写下划线」形状的字符串字面量
全算进去,于是吞进了 **2 个不是环境变量的东西**;host 那一侧吞进了 **1 个不是主机名的东西**。
逐个点名(锚点后紧跟的反引号即该处原文):

| 误吞项 | 锚点 + 原文 | 它其实是什么 |
|---|---|---|
| `REQUEST_RELEASE` | `plugins/browser/browserbase/provider.py:236`:`"status": "REQUEST_RELEASE",` | Browserbase 释放会话时提交的**状态值** |
| `VALID_REQUEST_TYPES` | `plugins/google_meet/node/__init__.py:53`:`"VALID_REQUEST_TYPES",` | 子包 `__all__` 里的一个**导出名** |
| host `meet` | `plugins/google_meet/meet_bot.py:44`:`r"^https://meet\.google\.com/("` | 一条**正则**,被 URL 抽取器在反斜杠处截断 |

**人工归类后:真实环境变量 = 38 条,真实主机 = 22 个。**
逐条清单见 `data/r11f/e/credential-egress.txt`。

**按 provider 归并的凭据来源全表**(38 条按插件分组)。表里的 `get_secret` 指作用域感知读取器,
它比 `os.environ.get` 多走一层秘密源:

`agent/secret_scope.py:132 @ 863e313`

```
def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
```

| 插件 | 主凭据 | 读取方式 | 附带的可选 env |
|---|---|---|---|
| `image_gen/deepinfra` | `DEEPINFRA_API_KEY` | `get_secret` | `DEEPINFRA_IMAGE_MODEL` |
| `image_gen/fal` | `FAL_KEY` | 委托 `tools/image_generation_tool.py` | — |
| `image_gen/krea` | `KREA_API_KEY` **或** Nous 托管网关 | `get_secret` + `resolve_managed_tool_gateway("krea")` | `KREA_IMAGE_MODEL` |
| `image_gen/openai` | `OPENAI_API_KEY` | `get_secret` | `OPENAI_IMAGE_MODEL` |
| `image_gen/openai-codex` | **ChatGPT/Codex OAuth**(无 env) | Codex Responses 适配层 | `OPENAI_IMAGE_MODEL` |
| `image_gen/openrouter` | `OPENROUTER_API_KEY`(provider `openrouter`) | `hermes_cli/runtime_provider.py` 的 `resolve_runtime_provider` | `OPENROUTER_IMAGE_MODEL` |
| `image_gen/openrouter` | **Nous OAuth**(provider `nous`) | 同上,`runtime_name="nous"` | `NOUS_IMAGE_MODEL` |
| `image_gen/xai` | xAI OAuth **或** `XAI_API_KEY` | `tools/xai_http.py:257` 的 `resolve_xai_http_credentials` | `XAI_IMAGE_MODEL` |
| `video_gen/deepinfra` | `DEEPINFRA_API_KEY` | 基类 `_env_key` + `os.environ.get` | `DEEPINFRA_BASE_URL`(由基类按 `name.upper()` 拼出) |
| `video_gen/fal` | `FAL_KEY` **或** Nous 托管网关(`fal-queue`) | `fal_key_is_configured()` + `resolve_managed_tool_gateway` | `FAL_VIDEO_MODEL` |
| `video_gen/xai` | xAI OAuth **或** `XAI_API_KEY` | `resolve_xai_http_credentials`,失败时兜底 `os.getenv` | `XAI_BASE_URL` |
| `browser/browser_use` | `BROWSER_USE_API_KEY` **或** Nous 托管网关(`browser-use`) | `get_secret` + `resolve_managed_tool_gateway` | — |
| `browser/browserbase` | `BROWSERBASE_API_KEY` **+** `BROWSERBASE_PROJECT_ID`(**唯一需要两条**) | `get_secret` | `BROWSERBASE_BASE_URL`、`BROWSERBASE_PROXIES`、`BROWSERBASE_ADVANCED_STEALTH`、`BROWSERBASE_KEEP_ALIVE`、`BROWSERBASE_SESSION_TIMEOUT` |
| `browser/firecrawl` | `FIRECRAWL_API_KEY` | `get_secret` | `FIRECRAWL_API_URL`、`FIRECRAWL_BROWSER_TTL` |
| `spotify` | **Spotify PKCE OAuth**(无 env) | `hermes_cli/auth.py` 的 `resolve_spotify_runtime_credentials` | (在 auth.py 侧:`HERMES_SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_ID` / `HERMES_SPOTIFY_REDIRECT_URI` / `SPOTIFY_REDIRECT_URI` / `HERMES_SPOTIFY_API_BASE_URL` / `HERMES_SPOTIFY_ACCOUNTS_BASE_URL`) |
| `google_meet` | `OPENAI_API_KEY`(仅 v2 realtime 用)| `get_secret` | 12 条 `HERMES_MEET_*`(见 2.9)、`PULSE_SOURCE` |

**这张表最重要的结构事实:凭据的「归属」与目录不重合。**
`plugins/spotify/` 整个目录里**零个 env 变量字面量、零个 URL 字面量** ——
它的凭据面与外发面**全部在 `hermes_cli/auth.py` 里**。所以「读一个插件目录就知道它要什么密钥」
这个直觉在本片是**错的**:manifest 的 `requires_env` 也不覆盖它(spotify 的 manifest 里没有 `requires_env`)。
凭据面的**唯一可靠读法是 `get_setup_schema()` 的 `env_vars` 字段**,那是给
`hermes tools` 画配置向导用的、每个 provider 自己声明的输入面。

**四个「托管网关(Nous 订阅代付)」接入点逐个列全**:

```verify
cd /home/user/hermes-agent && grep -rn "resolve_managed_tool_gateway(" plugins/browser plugins/google_meet plugins/image_gen plugins/spotify plugins/video_gen --include=*.py | sort
```

```text
plugins/browser/browser_use/provider.py:150:        managed = resolve_managed_tool_gateway(
plugins/image_gen/krea/__init__.py:185:        return resolve_managed_tool_gateway("krea")
plugins/video_gen/fal/__init__.py:339:    return resolve_managed_tool_gateway("fal-queue")
```

**片内 3 条 + 片外 1 条**:

| 插件 | 锚点 + 原文 | 网关名 |
|---|---|---|
| `browser/browser_use` | `plugins/browser/browser_use/provider.py:150`:`managed = resolve_managed_tool_gateway(` | `browser-use` |
| `image_gen/krea` | `plugins/image_gen/krea/__init__.py:185`:`return resolve_managed_tool_gateway("krea")` | `krea` |
| `video_gen/fal` | `plugins/video_gen/fal/__init__.py:339`:`return resolve_managed_tool_gateway("fal-queue")` | `fal-queue` |
| `image_gen/fal`(**片外**) | `tools/image_generation_tool.py:452`:`def _resolve_managed_fal_gateway():` | (FAL,间接) |

第四条在片外,所以上面那条命令看不见它 —— **搜索面是片内五个目录,不是全仓**。

**三条真实接入点共用同一条「谁优先」的判据** —— `tools/tool_backend_helpers.prefers_gateway(<域>)`:
有直连密钥且用户没显式要求走网关时,直连赢;`tool_gateway.<域>: gateway` 一设,网关赢。

### 2.6 接缝 F —— 外发面(22 个主机逐条)

按「这是真的会发请求的端点」还是「只是文档里的注册链接」分两类:

| 主机 | 类别 | 谁发 |
|---|---|---|
| `api.x.ai` | **请求端点** | `image_gen/xai`(`/v1/images/generations`、`/v1/images/edits`)、`video_gen/xai`(异步 videos API) |
| `api.deepinfra.com` | **请求端点** | `image_gen/deepinfra`(`/v1/openai/images/generations` + 目录发现)、`video_gen/deepinfra`(`/v1/openai/videos`) |
| `api.krea.ai` | **请求端点** | `image_gen/krea`(提交 + `GET /jobs/{id}` 轮询) |
| `api.browser-use.com` | **请求端点** | `browser/browser_use`(`/api/v3`) |
| `api.browserbase.com` | **请求端点** | `browser/browserbase` |
| `api.firecrawl.dev` | **请求端点** | `browser/firecrawl`(`/v2/browser`) |
| `meet.google.com` | **请求端点** | `google_meet`(Playwright 导航目标;URL 形状由 `plugins/google_meet/meet_bot.py:43` 的 `MEET_URL_RE` 白名单校验) |
| `accounts.google.com` | **请求端点** | `google_meet`(`hermes meet auth` 登录页) |
| `openrouter.ai` | 注册链接 | `image_gen/openrouter` 的 `get_setup_schema()`;真实 base_url 来自 `resolve_runtime_provider` |
| `platform.openai.com` | 注册链接 | `image_gen/openai` 的 `get_setup_schema()` |
| `chatgpt.com` | 注册链接 | `image_gen/openai-codex` 文案 |
| `fal.ai` | 注册链接 | `image_gen/fal`、`video_gen/fal` |
| `deepinfra.com` | 注册链接 | 两个 deepinfra 插件 |
| `www.krea.ai` / `docs.krea.ai` | 注册链接 / 文档 | `image_gen/krea` |
| `browser-use.com` / `browserbase.com` / `firecrawl.dev` | 注册链接 | 三个 browser 插件 |
| `console.x.ai` / `docs.x.ai` | 注册链接 / 文档 | `video_gen/xai` |
| `github.com` | 文档 | `image_gen/openrouter` 注释里的 issue 链接 |
| `brew.sh` | 文档 | macOS 安装提示 —— `plugins/google_meet/cli.py:311`:`"  install Homebrew first (https://brew.sh) or install the packages manually."` |

**`api.spotify.com` 不在这张表里** —— 它不在插件目录里,而在 auth 层:

`hermes_cli/auth.py:126 @ 863e313`

```
DEFAULT_SPOTIFY_ACCOUNTS_BASE_URL = "https://accounts.spotify.com"
DEFAULT_SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
```

**搜索面**:`plugins/{browser,google_meet,image_gen,spotify,video_gen}` 下全部 `.py`,
用 AST 取字符串常量再正则匹配 `https?://`(不是逐行 grep,因此跨行拼接的 URL 也能抓到常量部分);
排除了 `.md` / `.yaml`(它们不产生请求)。

### 2.7 接缝 G —— 工具面(12 个工具逐条)

| 工具 | toolset | schema/handler | 门禁 `check_fn` |
|---|---|---|---|
| `meet_join` / `meet_status` / `meet_transcript` / `meet_leave` / `meet_say` | `google_meet` | `plugins/google_meet/tools.py` | `check_meet_requirements` |
| `spotify_playback` / `spotify_devices` / `spotify_queue` / `spotify_search` / `spotify_playlists` / `spotify_albums` / `spotify_library` | `spotify` | `plugins/spotify/tools.py` | `_check_spotify_available` |

**两组的门禁语义相同,是一条可迁移的设计**:工具**始终注册**(所以在
`hermes tools` 里看得见、可被发现),但 `check_fn` 在运行期决定能不能派发。
对比之下 `image_generate` 的 `check_fn` 在没有后端时**直接返回 False**,
于是工具压根不会出现在模型的工具列表里:

`tools/image_generation_tool.py:1099 @ 863e313`

```
    configured = _read_configured_image_provider()
    if not configured or configured == "fal":
        return False
```

**同一个仓库里两种「不可用怎么表现」的做法并存**,值得在成品章里点出来。

另外三个能力域的工具**不在本片**,它们注册在 `tools/` 下:

| 工具 | 锚点 + 原文 |
|---|---|
| `image_generate` | `tools/image_generation_tool.py:1658`:`registry.register(` |
| `video_generate` | `tools/video_generation_tool.py:237`:`provider = get_active_provider()` |
| `browser_*` | `tools/browser_tool.py:735`:`def _get_cloud_provider() -> Optional[CloudBrowserProvider]:` |

本片的 13 个 provider 目录**一个工具都不注册** —— 它们只往注册表里放后端。
这正是 `kind: backend` 与 `kind: standalone` 的差别所在。

### 2.8 接缝 H —— `config.yaml` 键面(逐条列全)

| 键 | 读取处(锚点 + 该行原文) | 作用 |
|---|---|---|
| `image_gen.provider` | `agent/image_gen_registry.py:99`:`raw = section.get("provider")` | 注册表侧选生图后端 |
| `image_gen.provider` | `tools/image_generation_tool.py:1254`:`value = section.get("provider")` | 工具侧选生图后端(与上一行**是两处独立读取**) |
| `image_gen.model` | `tools/image_generation_tool.py:1230`:`value = section.get("model")` | 选模型(传给 provider 的 `model` kwarg) |
| `image_gen.max_parallel_requests` | `agent/tool_executor.py:215`:`image_gen.get("max_parallel_requests")` | 生图并发上限 |
| `image_gen.deepinfra.*` | `plugins/image_gen/deepinfra/__init__.py:65`:`di_section = section.get("deepinfra") if isinstance(section, dict) else None` | 后端私有覆盖 |
| `image_gen.krea.model` | `plugins/image_gen/krea/__init__.py:148`:`krea_cfg = cfg.get("krea") if isinstance(cfg.get("krea"), dict) else {}` | 同上 |
| `image_gen.krea.creativity` | `plugins/image_gen/krea/__init__.py:211`:`cfg_value = krea_cfg.get("creativity") if isinstance(krea_cfg, dict) else None` | 同上 |
| `image_gen.openai.model` | `plugins/image_gen/openai/__init__.py:105`:`openai_cfg = cfg.get("openai") if isinstance(cfg.get("openai"), dict) else {}` | 同上 |
| `image_gen.openai-codex.model` | `plugins/image_gen/openai-codex/__init__.py:165`:`sub = cfg.get("openai-codex") if isinstance(cfg.get("openai-codex"), dict) else {}` | 同上 |
| `image_gen.openrouter.model` / `image_gen.nous.model` | `plugins/image_gen/openrouter/__init__.py:272`:`scoped = cfg.get(self._config_key) if isinstance(cfg.get(self._config_key), dict) else {}` | 同上,**键名来自实例的 `_config_key`,一个类服务两个命名空间** |
| `image_gen.xai.model` | `plugins/image_gen/xai/__init__.py:96`:`xai_section = section.get("xai") if isinstance(section, dict) else None` | 同上 |
| `image_gen.xai.resolution` | `plugins/image_gen/xai/__init__.py:120`:`res = cfg.get("resolution") if isinstance(cfg.get("resolution"), str) else None` | 同上 |
| `video_gen.provider` | `agent/video_gen_registry.py:90`:`section = cfg.get("video_gen") if isinstance(cfg, dict) else None` | 选生视频后端 |
| `video_gen.fal.model` | `plugins/video_gen/fal/__init__.py:221`:`fal_cfg = cfg.get("fal") if isinstance(cfg.get("fal"), dict) else {}` | 选模型 |
| `video_gen.model` | `plugins/video_gen/fal/__init__.py:224`:`top = cfg.get("model")` | 选模型(次级) |
| `browser.cloud_provider` | `tools/browser_tool.py:762`:`if isinstance(browser_cfg, dict) and "cloud_provider" in browser_cfg:` | 选云浏览器后端(`local` = 关掉云模式) |
| `tool_gateway.browser` / `.image_gen` / `.video_gen` | `tools/tool_backend_helpers.py:278`:`def prefers_gateway(config_section: str) -> bool:` | 直连 vs 托管网关的优先级 |

**「后端私有模型覆盖」的三级优先级在片内是一致的约定**(env → `<域>.<后端>.model` → `<域>.model`),
七个生图后端里有六个逐字实现了同一条链;唯一的例外是 `deepinfra`,它把
`image_gen.model` 的读取合并进了同一次 `load_config()` 以省一次深拷贝。

### 2.9 接缝 I —— google_meet 特有的四个接缝

google_meet 不参与 provider 池,它自己是一套小系统。四个接缝逐个列全:

**(a) CLI 子命令面** —— `hermes meet <子命令>`,9 + 6 个:

| 层 | 子命令 |
|---|---|
| `plugins/google_meet/cli.py` 的 `register_cli` | `setup`、`install`、`auth`、`join`、`status`、`transcript`、`say`、`stop`、`node` |
| `plugins/google_meet/node/cli.py` 的子树 | `run`、`list`、`approve`、`remove`、`status`、`ping` |

**(b) 钩子面** —— 唯一一个:`on_session_end`。

`plugins/google_meet/__init__.py:103 @ 863e313`

```
    ctx.register_hook("on_session_end", _on_session_end)
```

回调 `_on_session_end` 的职责是「会话结束时如果 bot 还活着就让它离会」,**吞掉一切异常**
(会话结束不能因为清理失败而失败)。

**(c) 文件 IPC 面** —— 主进程与 bot 子进程**只通过文件通信,没有任何其它 IPC**。
路径面逐条:

| 路径 | 写者 | 读者 |
|---|---|---|
| `$HERMES_HOME/workspace/meetings/.active.json` | `process_manager` | `process_manager`(跨轮次找回 bot)、`node/server.py` |
| `$HERMES_HOME/workspace/meetings/<meeting-id>/status.json` | `meet_bot`(每 tick 刷) | `process_manager.status()` |
| `$HERMES_HOME/workspace/meetings/<meeting-id>/transcript.txt` | `meet_bot`(追加) | `process_manager.transcript()` |
| `$HERMES_HOME/workspace/meetings/<meeting-id>/say_queue.jsonl` | `process_manager.say()` / `node/server.py` 的 `say` 分支 | `meet_bot` 的 realtime speaker 线程 |
| `$HERMES_HOME/workspace/meetings/<meeting-id>/say_processed.jsonl` | `meet_bot` | (审计) |
| `$HERMES_HOME/workspace/meetings/nodes.json` | `node/registry.py` | gateway 侧解析 `node=<名>` |
| `$HERMES_HOME/workspace/meetings/node_token.json` | `node/server.py`(首启铸 token,chmod 0600) | `node/server.py` 后续启动 |

**bot 的输入面同样是「只经 env」**:12 条 `HERMES_MEET_*` 变量由
`process_manager` 组装进子进程环境 —— `HERMES_MEET_URL`、`HERMES_MEET_OUT_DIR`、
`HERMES_MEET_GUEST_NAME`、`HERMES_MEET_HEADED`、`HERMES_MEET_AUTH_STATE`、
`HERMES_MEET_DURATION`、`HERMES_MEET_MODE`、`HERMES_MEET_REALTIME_MODEL`、
`HERMES_MEET_REALTIME_VOICE`、`HERMES_MEET_REALTIME_INSTRUCTIONS`、
`HERMES_MEET_REALTIME_KEY`、`HERMES_MEET_LOBBY_TIMEOUT`。
**这是一条干净的进程边界设计**:bot 可以脱离 hermes 单独跑起来调试(模块 docstring 里就给了命令)。

**(d) 远程 node 的 RPC 面** —— 6 种请求类型,由协议模块用 frozenset 白名单钉死:

`plugins/google_meet/node/protocol.py:21 @ 863e313`

```
VALID_REQUEST_TYPES = frozenset({
    "start_bot",
    "stop",
    "status",
    "transcript",
    "say",
    "ping",
})
```

客户端侧 `plugins/google_meet/node/client.py` 恰好六个公开方法一一对应
(`start_bot` / `stop` / `status` / `transcript` / `say` / `ping`),
服务端六个 `if t == …` 分支也一一对应
(`plugins/google_meet/node/server.py:119`:`            if t == "ping":`)。
**三处必须同时改才能加一种请求** —— 这是这个小协议刻意付出的代价,换来的是
「非法 type 在编码阶段就被 `make_request` 拒绝,压根发不出去」。

`start_bot` 的 payload 还有**第二层白名单**:

`plugins/google_meet/node/server.py:124 @ 863e313`

```
                # Whitelist kwargs we pass through to pm.start.
                kwargs = {
                    k: payload[k]
                    for k in ("url", "guest_name", "duration", "headed",
                              "auth_state", "session_id", "out_dir")
                    if k in payload
                }
```

即**远端不能靠多塞一个字段去驱动本机 `pm.start()` 的任意参数**。
鉴权是共享 bearer token,在 `_handle_request` 分派**之前**校验,失败走信封级 error 通道:

`plugins/google_meet/node/server.py:106 @ 863e313`

```
        expected = self.ensure_token()
        ok, reason = _proto.validate_request(msg, expected)
        if not ok:
            return _proto.make_error(str(msg.get("id") or ""), reason)
```

---

## 3. 判据 3 · 端到端链:一次生图请求的完整走法

场景:用户在 Telegram 里说「画一张日落」,`image_gen.provider: xai` 已配置。

| # | 位置 | 发生什么 |
|---|---|---|
| 1 | `tools/image_generation_tool.py:1658` 的 `registry.register(` | 进程启动时 `image_generate` 工具入册,`toolset="image_gen"`,`check_fn=check_image_generation_requirements`,并挂一个 `dynamic_schema_overrides` |
| 2 | `tools/image_generation_tool.py:1611` 的 `_build_dynamic_image_schema` | 工具描述**按当前后端能力动态生成** —— 若活动后端只支持文生图,schema 里就明说 `image_url` 不被支持,省掉模型白试一轮 |
| 3 | 模型发出 `tool_call: image_generate` | — |
| 4 | `agent/tool_executor.py:235` 的 `== "image_generate"` | 这一批工具调用里只要有 `image_generate`,并发上限就被压到 `image_gen.max_parallel_requests` |
| 5 | `tools/image_generation_tool.py:1513` 的 `_dispatch_to_plugin_provider(` | 进入插件派发 |
| 6 | `tools/image_generation_tool.py:1283`:`configured = _read_configured_image_provider()` | 读 `image_gen.provider`;**未设或等于 `"fal"` 就直接返回 None**,落回内建 FAL 路径 |
| 7 | `tools/image_generation_tool.py:1296` 的 `_ensure_plugins_discovered()` | 触发插件发现(幂等);若首次没找到,`:1307` 再 `force=True` 重试一次 |
| 8 | `plugins/image_gen/xai/__init__.py:492` 的 `def register(ctx: Any) -> None:` | 发现过程中执行,`ctx.register_image_gen_provider(XAIImageGenProvider())` |
| 9 | `hermes_cli/plugins.py:682` 的 `if not isinstance(provider, ImageGenProvider):` | 类型门禁:不是 ABC 实例就 WARNING 后忽略 |
| 10 | `agent/image_gen_registry.py:51` 的 `with _lock:` | 加锁写进注册表 |
| 11 | `tools/image_generation_tool.py:1297` 的 `provider = get_provider(configured)` | 按名取出 xai provider |
| 12 | `plugins/image_gen/xai/__init__.py:231` 的 `creds = resolve_xai_http_credentials()` | 解析凭据:优先 xAI OAuth,其次 `XAI_API_KEY` |
| 13 | `plugins/image_gen/xai/__init__.py:336` 的 `response = requests.post(` | **外发**:POST `https://api.x.ai/v1/images/generations`,120s 超时 |
| 14 | `plugins/image_gen/xai/__init__.py:434` 的 `saved_path = save_url_image(url, prefix=f"xai_{model_id}")` | xAI 返回的是**短命 URL**,必须当场落盘(见下) |
| 15 | `agent/image_gen_provider.py:272` 的 `def save_url_image(` | 下载到 `$HERMES_HOME/cache/images/`,25MB 上限、按 Content-Type 推扩展名、0 字节拒收 |
| 16 | `plugins/image_gen/xai/__init__.py:476` 的 `return success_response(` | 组装统一响应字典 |
| 17 | `tools/image_generation_tool.py:1519` 的 `_postprocess_image_generate_result(` | 若终端后端与宿主不同文件系统,补 `host_image` / `agent_visible_image` 两个字段并强制同步产物 |
| 18 | `gateway/run.py:1628` 的 `if tool_name == "image_generate" and "MEDIA:" not in content:` | gateway 从 JSON 里**自动提取路径**,不依赖模型在最终回复里复述 |
| 19 | `gateway/run.py:1557` 的 `_JSON_MEDIA_TOOL_PATH_FIELDS = ("host_image", "image", "agent_visible_image")` | 依次尝试三个字段 |
| 20 | `gateway/run.py:1564` 的 `_TOOL_MEDIA_RE = re.compile(` | **只认绝对路径**(`/`、`~/`、`C:\`)且扩展名在白名单里 |
| 21 | 平台适配器 `send_photo` | 图片到达用户 |

**第 14 步是这条链上最有教学价值的一处**,它把「provider 层的一个实现细节」与
「gateway 层的一条正则」耦合了起来:

`plugins/image_gen/xai/__init__.py:425 @ 863e313`

```
        elif url:
            # xAI's grok-imagine-image returns ephemeral ``imgen.x.ai/xai-tmp-*``
            # URLs that 404 within minutes — by the time Telegram's
            # ``send_photo`` or any downstream consumer fetches them, the
            # asset is gone (#26942).  Materialise the bytes locally at
            # tool-completion time so the gateway has a stable file path to
            # upload, mirroring the b64 branch above and the audio_cache
            # pattern used by text_to_speech.
```

**事故讲成因果**:xAI 的生图接口返回一个 `imgen.x.ai/xai-tmp-*` 的临时 URL,几分钟后 404。
模型拿到这个 URL 写进回复,gateway 走到第 20 步 —— `_TOOL_MEDIA_RE` 要求路径以
`/` 或盘符开头,`https://...` **匹配不上**,于是这张图**根本不会被当作附件发出去**;
就算它匹配上了,等 Telegram 真去取那个 URL 时资产也已经没了。
修法不是改 gateway 的正则,而是**让 provider 在返回前把字节落到本地**,
于是第 19 步的 `image` 字段变成一个绝对路径,第 20 步顺利通过。
**可迁移的原则:跨层交付媒体时,把"这个引用还能活多久"当成契约的一部分。**
溯源:issue #26942。

---

## 4. 判据 4 · 逐字取证清单

本底稿的逐字源码围栏块共 **27 个**(全部整块逐字,`BLOCK-DRIFT` 为 0)。按出现顺序:

| # | 锚点 + 块首行原文 | 证明什么 |
|---|---|---|
| 1 | `hermes_cli/plugins.py:1657`:`return PluginManifest(` | manifest 读取面只有 8 个键 |
| 2 | `plugins/image_gen/openrouter/__init__.py:523`:`def register(ctx: Any) -> None:` | 一个 `register()` 注册多个 provider |
| 3 | `agent/image_gen_provider.py:136`:`def default_model(self) -> Optional[str]:` | 基类默认取 `list_models()[0]` |
| 4 | `agent/image_gen_provider.py:74` 的 `Stable short identifier used in` | 生图 `name` 的语义 |
| 5 | `agent/browser_provider.py:65` 的 `Stable short identifier used in the` | 浏览器 `name` 的语义(允许连字符) |
| 6 | `agent/browser_registry.py:107`:`_LEGACY_PREFERENCE = (` | 浏览器自动探测的偏好表 |
| 7 | `agent/browser_registry.py:103` 的 `Matches the pre-migration walk in` | 排除 firecrawl 的理由 |
| 8 | `agent/secret_scope.py:132`:`def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:` | 作用域感知的凭据读取器 |
| 9 | `hermes_cli/auth.py:126`:`DEFAULT_SPOTIFY_ACCOUNTS_BASE_URL = "https://accounts.spotify.com"` | Spotify 外发面在 auth 层 |
| 10 | `tools/image_generation_tool.py:1099`:`configured = _read_configured_image_provider()` | 生图 `check_fn` 无后端即 False |
| 11 | `plugins/google_meet/__init__.py:103`:`ctx.register_hook("on_session_end", _on_session_end)` | 唯一的钩子注册 |
| 12 | `plugins/google_meet/node/protocol.py:21`:`VALID_REQUEST_TYPES = frozenset({` | node RPC 的 6 种请求类型 |
| 13 | `plugins/google_meet/node/server.py:124` 的 `# Whitelist kwargs we pass through to pm.start.` | start_bot 的第二层参数白名单 |
| 14 | `plugins/google_meet/node/server.py:106`:`expected = self.ensure_token()` | 鉴权先于分派 |
| 15 | `plugins/image_gen/xai/__init__.py:425`:`elif url:` | 短命 URL 必须落盘的因果 |
| 16 | `tools/image_generation_tool.py:1283`:`configured = _read_configured_image_provider()` | 未配置就不碰注册表(▲-1) |
| 17 | `tools/video_generation_tool.py:233` 的 `from agent.video_gen_registry import get_active_provider` | 生视频侧真的调 `get_active_provider()` |
| 18 | `tools/image_generation_tool.py:1078`:`lines.append(` | 指向 `hermes tools` 的那句文案 |
| 19 | `tools/browser_tool.py:738` 的 `Reads ``config["browser"]["cloud_provider"]`` once and caches the result` | ▲(码内)-1 的 docstring |
| 20 | `tools/browser_tool.py:819`:`try:` | 自动探测分支硬编码两个内建类 |
| 21 | `agent/browser_registry.py:113`:`def _resolve(configured: Optional[str]) -> Optional[BrowserProvider]:` | 生产死代码的定义处 |
| 22 | `tools/browser_tool.py:779` 的 `# Ensure plugins are discovered so the registry is` | 显式配置路径**认**注册表 |
| 23 | `tools/browser_tool.py:810` 的 `# Auto-detect path: Browser Use first (managed Nous gateway or` | 为可打桩而绕过注册表的自述 |
| 24 | `plugins/google_meet/plugin.yaml:15`:`hooks:` | ■-2 的清单键 |
| 25 | `hermes_cli/plugins.py:291`:`requires_env: List[Union[str, Dict[str, Any]]] = field(default_factory=list)` | `provides_hooks` 字段定义 |
| 26 | `hermes_cli/plugins_cmd.py:1855` 的 `for tool_name in manifest.get("provides_tools") or []:` | `provides_tools` 有真消费方 |
| 27 | `plugins/image_gen/openrouter/__init__.py:485`:`def _build_providers() -> List[OpenRouterCompatImageProvider]:` | ◇-1 的构造处 |

---

## 5. 判据 5 · 记号

### ▲(地图级)· 1 条

**▲-1 生图插件文档说工具向注册表要「活动 provider」,代码不是这么做的。**

涉事两句在「## How discovery works」标题下,整段一并判定:

`website/docs/developer-guide/image-gen-provider-plugin.md:23 @ 863e313`

> Each plugin's `register(ctx)` function calls `ctx.register_image_gen_provider(...)` — that puts it into the registry in `agent/image_gen_registry.py`. The active provider is picked by `image_gen.provider` in `config.yaml`; `hermes tools` walks users through selection.

`website/docs/developer-guide/image-gen-provider-plugin.md:25 @ 863e313`

> The `image_generate` tool wrapper asks the registry for the active provider and dispatches there. If no provider is registered, the tool surfaces a helpful error pointing at `hermes tools`.

**:23 成立**(前半句是注册链,后半句「由 `image_gen.provider` 选出」也对)。
**:25 的第一句不成立**:工具包装器从不向注册表要「活动 provider」;
它先读 `image_gen.provider`,**未设或等于 `"fal"` 时根本不碰注册表**:

`tools/image_generation_tool.py:1283 @ 863e313`

```
    configured = _read_configured_image_provider()
    if not configured or configured == "fal":
        return None  # unset/explicit FAL keeps the legacy FAL path
```

而注册表自己是**有** `get_active_provider()` 的,而且它在未配置时会兜底选中唯一那个可用后端。
两条路径给出的答案在同一份注册表状态下就不一样:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python /home/user/hermes-study/data/r11f/probes/e_active_provider_gap.py 2>/dev/null
```

```text
image.registry.get_active_provider = 'probe-solo-image'
image.tool.dispatch = None
image.tool.calls_get_active_provider = False
video.registry.get_active_provider = 'probe-solo-video'
video.tool.calls_get_active_provider = True
image: registry-active == tool-dispatch ? False
```

即:**注册了恰好一个可用生图后端、`image_gen.provider` 未设**时,
注册表说「活动后端是它」,而 `image_generate` 落回内建 FAL 路径。
`video_gen` 那一侧是对的 —— 生视频派发器真的调了注册表的 `get_active_provider()`:

`tools/video_generation_tool.py:233 @ 863e313`

```
        from agent.video_gen_registry import get_active_provider
        from hermes_cli.plugins import _ensure_plugins_discovered

        _ensure_plugins_discovered()
        provider = get_active_provider()
        if provider is None:
            _ensure_plugins_discovered(force=True)
            provider = get_active_provider()
        return provider
```

**同一份文档模板套在两个域上,只有一个域的实现对得上。**

第二句(「没有 provider 注册时给出指向 `hermes tools` 的友好错误」)属**半真**:

`tools/image_generation_tool.py:1078 @ 863e313`

```
    lines.append(
        "  3. Configure a different image_gen provider via `hermes tools` "
        "→ Image Generation (run `hermes plugins list` to see installed "
        "backends)"
    )
```

—— 它的确把用户指向 `hermes tools`,但这是**内建 FAL 路径**的「FAL 不可达」文案,
触发条件不是「没有 provider 注册」;而且工具的 `check_fn` 会**先**返回 False
(上面 §2.7 那个 `tools/image_generation_tool.py:1099` 的块),
把工具**整个挡在模型的工具列表之外** —— 用户看到的不是错误,而是「工具不见了」。

### ▲(码内)· 1 条(与地图级分开计数)

**▲(码内)-1 `_get_cloud_provider` 的 docstring 说自动探测「现在表达为 `_LEGACY_PREFERENCE` 的遍历」,代码里没有任何一处读它。**

`tools/browser_tool.py:738 @ 863e313`

```
    Reads ``config["browser"]["cloud_provider"]`` once and caches the result
    for the process lifetime. An explicit ``local`` provider disables cloud
    fallback. If unset, fall back to Browser Use (managed Nous gateway or
    direct API key) and then Browserbase (direct credentials only) — the
    historic auto-detect order, now expressed as the
    :data:`agent.browser_registry._LEGACY_PREFERENCE` walk.
```

实际的自动探测分支直接 `new` 两个内建类:

`tools/browser_tool.py:819 @ 863e313`

```
        try:
            fallback_provider = BrowserUseProvider()
            if fallback_provider.is_configured():
                resolved = fallback_provider
            else:
                fallback_provider = BrowserbaseProvider()
                if fallback_provider.is_configured():
                    resolved = fallback_provider
```

「顺序一致」是真的,「表达为那个遍历」是假的 —— 顺序在这里是**手写重复**的,
`_LEGACY_PREFERENCE` 在生产代码里只出现在两条注释里(`tools/browser_tool.py:743`、`:818`)。

### ■(代码缺陷)· 2 条

**■-1 浏览器注册表的 `_resolve()` 是生产死代码,导致同名覆盖在自动探测路径上失效。**

`agent/browser_registry.py:113 @ 863e313`

```
def _resolve(configured: Optional[str]) -> Optional[BrowserProvider]:
    """Resolve the active browser provider.
```

它用 33 行 docstring 写清了三条选择规则并实现了它们,但生产代码零调用方 ——
唯一的调用者是测试。搜索面与读数:

```verify
cd /home/user/hermes-agent && echo "-- all .py refs to browser_registry --" && grep -rn "browser_registry" --include=*.py . | wc -l && echo "-- non-test refs --" && grep -rn "browser_registry" --include=*.py . | grep -v "^\./tests/" && echo "-- _resolve( call sites, whole repo --" && grep -rn "_resolve(" --include=*.py . | grep -i browser
```

```text
-- all .py refs to browser_registry --
20
-- non-test refs --
./hermes_cli/plugins.py:807:        from agent.browser_registry import register_provider as _register_browser_provider
./hermes_cli/tools_config.py:2994:        from agent.browser_registry import list_providers as _list_browser_providers
./tools/browser_tool.py:165:from agent.browser_registry import (  # noqa: F401  (test-patchable surface)
./tools/browser_tool.py:658:# :mod:`agent.browser_registry` at plugin-discovery time. The legacy
./tools/browser_tool.py:662:# :mod:`agent.browser_registry` for the actual lookup.
./tools/browser_tool.py:743:    :data:`agent.browser_registry._LEGACY_PREFERENCE` walk.
./tools/browser_tool.py:745:    Selection routes through :mod:`agent.browser_registry` so third-party
./tools/browser_tool.py:818:        # :data:`agent.browser_registry._LEGACY_PREFERENCE`.
-- _resolve( call sites, whole repo --
./agent/browser_registry.py:113:def _resolve(configured: Optional[str]) -> Optional[BrowserProvider]:
./tests/plugins/browser/test_browser_provider_plugins.py:160:    """``_resolve()`` implements the documented three-rule precedence."""
./tests/plugins/browser/test_browser_provider_plugins.py:167:        assert _resolve(None) is None
./tests/plugins/browser/test_browser_provider_plugins.py:174:        assert _resolve("local") is None
./tests/plugins/browser/test_browser_provider_plugins.py:189:        provider = _resolve(None)
```

*(搜索面:全仓 `*.py`。`browser_registry` 共 **20** 处引用,其中 **8** 处非测试 ——
3 处是真 import(`register_provider` / `list_providers` / `get_provider`),5 处是注释/docstring,
**没有一处 import 或调用 `_resolve`**。`_resolve(` 在全仓的命中里,除定义处外
**全部落在 `tests/plugins/browser/test_browser_provider_plugins.py`**:`:167`、`:174`、`:189` 是调用,
`:160` 是那条测试的 docstring。最后这条 grep 加了 `| grep -i browser` 收窄,
所以它只覆盖名字里带 "browser" 的路径/行 —— 这对本结论够用,因为 `_resolve` 是
`agent/browser_registry` 的模块私有名,任何调用方都得先 import 这个模块,
而上一条命令已经把这 20 处 import/引用全列出来了。)*

**行为后果不是理论的**:注册表的 `register_provider` 文档化承诺「同名重注册覆盖前一个」,
用户可以往 `~/.hermes/plugins/browser/browser-use/` 放一个自己的实现顶掉内建那个。
显式配置路径**认**这个覆盖:

`tools/browser_tool.py:779 @ 863e313`

```
                    # Ensure plugins are discovered so the registry is
                    # populated. Idempotent — cheap on subsequent calls.
                    _ensure_browser_plugins_loaded()
                    resolved = _registry_get_browser_provider(provider_key)
```

**自动探测路径不认**:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python /home/user/hermes-study/data/r11f/probes/e_browser_autodetect_bypass.py 2>/dev/null
```

```text
registry._resolve(None) -> ThirdPartyBrowserUse
browser_tool._get_cloud_provider() -> None
registered under 'browser-use': ThirdPartyBrowserUse
same object ? False
```

注册表里 `browser-use` 这个名字下坐着的是第三方实现且 `is_available()` 为真,
`_resolve(None)` 正确地选中它;而 `_get_cloud_provider()` 新建了一个**内建** `BrowserUseProvider()`,
它没有凭据于是 `is_configured()` 假,最终返回 None ——**用户的覆盖被静默忽略**。
代码自己写明了原因:

`tools/browser_tool.py:810 @ 863e313`

```
        # Auto-detect path: Browser Use first (managed Nous gateway or
        # direct API key), then Browserbase (direct credentials). Uses
        # the legacy class names imported at the top of this module so
        # tests that ``monkeypatch.setattr(browser_tool, "BrowserUseProvider", ...)``
        # keep driving this branch deterministically. Third-party browser
        # plugins are intentionally NOT reachable from auto-detect — they
        # participate only via explicit ``browser.cloud_provider: <name>``,
        # mirroring the firecrawl gate documented on
        # :data:`agent.browser_registry._LEGACY_PREFERENCE`.
```

即**为了测试可打桩而牺牲了注册表的单一真相地位**。注意最后一句还把这条分支说成
「参照 `_LEGACY_PREFERENCE` 上记录的 firecrawl 门禁」,而它并不读那个常量 —— 与 ▲(码内)-1 同源。

**■-2 google_meet 清单里的 `hooks:` 键,加载器不读;全仓 97 份 manifest 里 0 份用加载器读的那个拼写。**

`plugins/google_meet/plugin.yaml:15 @ 863e313`

```
hooks:
  - on_session_end
```

加载器读的是 `provides_hooks`(见 §2.1 的逐字块 `provides_hooks=data.get("provides_hooks", []),`)。
全仓普查:

```verify
cd /home/user/hermes-agent && echo "manifests with '^hooks:' :" && grep -rlE "^hooks:" --include=plugin.yaml . | wc -l && echo "manifests with '^provides_hooks:' :" && grep -rlE "^provides_hooks:" --include=plugin.yaml . | wc -l && echo "total plugin.yaml :" && find . -name plugin.yaml | wc -l
```

```text
manifests with '^hooks:' :
10
manifests with '^provides_hooks:' :
0
total plugin.yaml :
97
```

**10 份 manifest 声明了钩子,0 份用加载器读的那个键名** —— 于是那个数据类字段:

`hermes_cli/plugins.py:291 @ 863e313`

```
    requires_env: List[Union[str, Dict[str, Any]]] = field(default_factory=list)
    provides_tools: List[str] = field(default_factory=list)
    provides_hooks: List[str] = field(default_factory=list)
```

对**每一个随仓发布的插件恒为空列表**。文档教的正是 `provides_hooks:` 这个拼写:

`website/docs/developer-guide/plugins/index.md:75 @ 863e313`

> This tells Hermes: "I'm a plugin called calculator, I provide tools and hooks." The `provides_tools` and `provides_hooks` fields are lists of what the plugin registers.

而同一份文档在 `website/docs/developer-guide/plugins/index.md:648` 与 `:1167` 的示例里
又写成 `hooks:` —— 拼写在文档内部就已经不自洽。

**当前影响是潜伏的**:`provides_hooks` 在非测试代码里没有消费方。
**搜索面**:`hermes_cli/` + `agent/` + `gateway/` + `tools/` 全部 `.py`,模式 `provides_hooks`,
命中 3 处 —— 数据类字段定义、`_parse_manifest` 里的解析赋值、`hermes_cli/web_server.py:1177`
的一句 docstring;没有任何一处读取它的值。
对照之下**同一对键里的 `provides_tools` 是有真消费方的**:

`hermes_cli/plugins_cmd.py:1855 @ 863e313`

```
                for tool_name in manifest.get("provides_tools") or []:
                    entry = registry.get_entry(tool_name)
                    if entry and entry.toolset:
                        return entry.toolset
```

—— 用来在插件未加载时反查 toolset。所以这不是「这类键都没用」,而是**这一个键漏接了**。

### ◇(代码有、文档无)· 1 条

**◇-1 一个插件目录可以注册多个 provider,文档的模型是一目录一后端。**

`plugins/image_gen/openrouter/__init__.py:485 @ 863e313`

```
def _build_providers() -> List[OpenRouterCompatImageProvider]:
    return [
        OpenRouterCompatImageProvider(
            provider_name="openrouter",
```

返回两个实例,`register()` 逐个注册。于是 `plugins/image_gen/` 下 7 个目录产出 8 个 provider(见 §2.2 读数)。
文档只描述「往 `plugins/image_gen/<name>/` 扔一个目录」这一种形状(见下面 ◎-1 引的那段),
没有提到一个 `register()` 可以注册任意多个后端 —— 而这正是
「同一套协议服务两个厂商(OpenRouter 与 Nous Portal)」这个真实需求的解法,值得写进成品章。

### ◎(文档成立但显著保守)· 1 条

**◎-1 文档列出的内建生图后端是 7 个,注册表里是 8 个。**

`website/docs/developer-guide/image-gen-provider-plugin.md:9 @ 863e313`

> Image-gen provider plugins register a backend that services every `image_generate` tool call — DALL·E, gpt-image, Grok, Flux, Imagen, Stable Diffusion, fal, Replicate, a local ComfyUI rig, anything. Built-in providers (OpenAI, OpenAI-Codex, xAI, FAL, Krea, DeepInfra, OpenRouter) all ship as plugins. You can add a new one, or override a bundled one, by dropping a directory into `plugins/image_gen/<name>/`.

括号里列的 7 个**每一个都成立**(它们确实都以插件形式随仓发布),句子字面为真,
所以按 CLAUDE.md 的口径**不是 ▲**;但注册表里第 8 个 `nous`(Nous Portal)没有出现在这份清单里,
而它恰恰是**订阅制用户的默认生图路径**。记 ◎。

**记号计数:▲(地图)1 · ▲(码内)1 · ■ 2 · ◇ 1 · ◎ 1。**

---

## 6. 可迁移的设计观察(给「自己造一个 harness」用)

1. **「一个能力 + 多个后端」的最小骨架是四件套**:ABC(契约)、registry(进程内 dict + 锁 + 同名覆盖)、
   `PluginContext.register_*`(类型门禁,坏插件只 WARNING 不抛)、配置键(选谁)。
   本片三个能力域用的是同一副骨架,差别只在 ABC 的方法面。
2. **有生命周期的资源要把清理提成抽象方法**。browser 的 ABC 把 `close_session` 与
   `emergency_cleanup` 都设成 `@abstractmethod`,并在 docstring 里明写「不许抛异常」——
   因为 `emergency_cleanup` 是从 atexit / 信号处理器里调的。
3. **显式配置要「即使不可用也返回」**。三个注册表都这么做,理由一致:
   静默换后端会让用户排查不出为什么账单跑到别家去了;抛一个精确错误反而是更好的服务。
4. **共享凭据的两个能力,自动探测只能认一个**(firecrawl 的取舍)。
5. **选择逻辑必须只有一处实现**。■-1 就是同一套规则写了两遍的代价:
   一份成了生产路径、一份成了只有测试在跑的规范,两者已经漂开而没人发现。
6. **跨层交付媒体时,引用的存活期是契约的一部分**(§3 第 14 步)。
7. **「不可用怎么表现」要在整个仓库里统一**。本片同时存在两种做法
   (工具照常注册但运行期拒绝 / 工具直接不出现),各有道理,但混用会让用户困惑。
8. **清单文件里的键要么被读、要么删掉**。本片 3 个键(§2.1)从未被读过,
   其中一个(`hooks`)还是全仓 10 份 manifest 的通用写法 —— **一份没人读的清单会慢慢变成谎话**。

---

## 7. 移交项

| 案号 | 现象(锚点 + 一句话) | 建议去向 |
|---|---|---|
| `H-R11F-E-a` | `tools/image_generation_tool.py:1284`:`if not configured or configured == "fal":` —— 生图工具从不调 `get_active_provider()`,与注册表 docstring 和 website 文档都对不上;`video_gen` 侧则调了。需要判定「哪一侧是意图」 | R12 装订前定案;若判为缺陷,是一条会影响「只装了一个后端」用户的真实路径 |
| `H-R11F-E-b` | `agent/browser_registry.py:113`:`def _resolve(configured: Optional[str]) -> Optional[BrowserProvider]:` —— 生产零调用方,自动探测在 `tools/browser_tool.py:820` 重复实现,导致同名覆盖失效 | 与片 F 的插件公共面合并看;这是「注册表是不是单一真相」的通用问题 |
| `H-R11F-E-c` | `plugins/google_meet/plugin.yaml:15`:`hooks:` —— 全仓 10 份 manifest 用 `hooks:`,加载器读 `provides_hooks`,97 份里 0 份用后者 | 片 F(插件公共面)已覆盖 `hermes_cli/plugins.py` 的清单解析,请合并定案 |
| `H-R11F-E-d` | `plugins/google_meet/plugin.yaml:6`:`platforms:` —— 清单声明 `[linux, macos]`,加载器不读;真正的门禁在 `plugins/google_meet/__init__.py:74` 的 `system = platform.system().lower()` | 同上,与 `H-R11F-E-c` 是同一族(声明键无消费方),但**是两个独立实体,不合号** |
| `H-R11F-E-e` | `plugins/browser/browser_use/plugin.yaml:6`:`provides_browser_providers:` —— 3 份 browser 清单都声明它,加载器不读;`website/docs/developer-guide/browser-provider-plugin.md:153` 把它列进了发布检查清单,与 `kind: backend`(真的被读)并列 | 建议在成品章里点明「哪些清单键是加载器读的、哪些只是文档」——这是插件作者最容易被误导的一处 |
| `H-R11F-E-f` | `plugins/spotify/plugin.yaml:5`:`kind: backend` —— spotify 注册的是**工具**不是后端,却标 `kind: backend`(理由写在 `plugins/spotify/__init__.py:18`:自动加载、不需要用户 opt-in)。`kind` 的语义因此在「注册什么」与「怎么加载」之间是含混的 | 片 F 的 `kind` 语义梳理;本片只记现象不下结论 |

---

## 8. 判据适用性复核(派工书要求的验收项)

五条判据在本片形态上**全部适用,无需修订**。一点补充建议:

**判据 2 应显式要求「注册面读数必须在运行期取」。** 本片给出了两处「数目录会数错」的实例:
① 7 个 `image_gen` 目录注册 8 个 provider;② 2 个 `register_tool` 调用点注册 12 个工具。
静态枚举(grep 目录、grep 调用点)在这两处都会给出**看起来合理但错误**的数。
这与 CLAUDE.md 里「同一指标多次/多方法测量必须分别标注」是同一条道理的延伸:
接缝的条数,静态口径与运行期口径可以不同,**报数时要说清是哪一个**。

---

## 完成信号

- **片号**:R11F 片 E —— `plugins/{google_meet, image_gen, video_gen, spotify, browser}`(50 文件 / 10,643 行)
- **产出文件**:
  - 底稿 `notes/r11f-raw-e-media-plugins.md`(本文件)
  - 探针 `data/r11f/probes/e_manifest_census.py`、`e_provider_contract.py`、
    `e_credential_egress.py`、`e_registration_surface.py`、`e_active_provider_gap.py`、
    `e_browser_autodetect_bypass.py`
  - 数据 `data/r11f/e/manifest-census.txt`、`provider-contract.txt`、`credential-egress.txt`、
    `registration-surface.txt`、`active-provider-gap.txt`、`browser-autodetect-bypass.txt`、
    `manifest-census-tail.txt`
- **五条判据**:
  1. **点名到位 —— 达成**。50 个文件全部出现全路径 + 一句话角色(§1.1–§1.5,
     分组 image_gen 14 / video_gen 6 / browser 9 / spotify 4 / google_meet 17 = 50,
     由 §1 那个 `verify` 块从派工清单复算,不靠手算)。
  2. **接缝穷举 —— 达成**。九个接缝逐项列全并给机械枚举命令与条数:
     清单键面 15 份 / 10 键(3 键无消费方)、注册入口 15 个、`ctx.register_*` 6 种 17 点、
     运行期 provider 14 个、ABC 契约面 3 域 14 实现 + 1 mixin、选择规则 3 域 3 套、
     env 变量 38 条(探针粗口径 40,已逐条交代 2 个误吞)、外发主机 22 个(粗口径 23,已交代 1 个误吞)、
     工具 12 个、config 键 17 行、google_meet 四个专有接缝(CLI 9+6、hook 1、文件 IPC 7 条路径 + 12 条 env、RPC 6 类型)。
  3. **端到端链 —— 达成**。一次生图请求 21 跳全部带锚点(§3)。
  4. **逐字取证 —— 达成**。**27 个**逐字源码围栏块,全部整块逐字(§4 清单);
     引用关卡 `BLOCK-DRIFT = 0`。
  5. **记号 —— 达成**。▲(地图)1 + ▲(码内)1 + ■ 2 + ◇ 1 + ◎ 1,全部带锚点(§5)。
- **点名文件数**:50 / 50。
- **接缝枚举命令与条数**(**12 条 `verify` 块,每条都配了 `text` 输出块;
  `verify_evidence_commands.py` 对本文件报 `paired=12 unpaired=0 differing=0`**):
  - 分组文件/行数复算(`awk` on `data/r11f/slices/E.txt`)→ 50 文件 / 10,643 行
  - `e_manifest_census.py | tail -14` → 15 manifest / 10 键 / 3 键 UNREAD
  - `grep -rn "^def register(" …` → 15
  - `grep -rho "ctx\.register_[a-z_]*" … | sort | uniq -c` → 6 种 / 17 点
  - `e_registration_surface.py` → 14 provider(image_gen 8 / video_gen 3 / browser 3)
  - `e_provider_contract.py` → 3 域 ABC 方法面 + 14 实现的三态表
  - `e_credential_egress.py | tail -2` → 40 env 形状 / 23 host(人工归类后 38 / 22)
  - `grep -rn "resolve_managed_tool_gateway(" …` → 3 条真实托管网关接入点
  - `e_active_provider_gap.py` → 生图两条路径答案不同(▲-1)
  - `e_browser_autodetect_bypass.py` → 自动探测绕过注册表(■-1)
  - `grep -rlE "^hooks:" --include=plugin.yaml` → 10 / 0 / 97(■-2)
- **新铸记号编号**:`H-R11F-E-a`、`H-R11F-E-b`、`H-R11F-E-c`、`H-R11F-E-d`、`H-R11F-E-e`、`H-R11F-E-f`(6 个,一号一实体)。
- **关卡读数**(本底稿单独口径,自校验读数按 CLAUDE.md 规矩不写进 `verify` 块):

```text
verify_citations.py  本文件:citations=36  OK=31  UNCHECKED=5   可校验比例 86.1%
                     table_anchors=84  OK=84  UNCHECKED=0
                     无 MISMATCH / BLOCK-DRIFT / TABLE-DRIFT / OUT-OF-RANGE
verify_citations.py  强制范围(chapters/* + 本文件):citations=515 OK=417 UNCHECKED=98  81.0%
                     table_anchors=117 OK=89 UNCHECKED=28;退出码 0
verify_evidence_commands.py  强制范围:paired=13 unpaired=0 differing=0 timedout=0;退出码 0
```

  当轮 notes 单独的可校验比例 **86.1%**,高于 70% 下限。
- **硬边界自查**:基线 `git status --porcelain` 为空;所有执行基线代码的命令带
  `HERMES_DISABLE_LAZY_INSTALLS=1`,探针开头断言 `_allow_lazy_installs() = False`;
  未改 `scripts/`、`chapters/`、台账、`CLAUDE.md`;未动 `data/inflight/*.claim`;
  未扩充 venv(仍 **87 包**);未向任何第三方 API 发请求
  (三个导入型探针只注册假 provider、读临时 `HERMES_HOME` 下的配置,无网络调用)。
