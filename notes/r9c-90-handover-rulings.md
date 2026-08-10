# r9c-90 · 移交项定案(主线独立取证)

> 本轮(R9C)归属的 R9A / R9B 移交项,全部由主线亲自取证,不转述子代理。
> 溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 实验脚本一律只用 `127.0.0.1` 上的本地端口,不出网、不改基线。

## 本轮归属的移交项

| 移交项 | 来源 | 本轮结论 |
|---|---|---|
| **H-R9A-a** = **H-R9B-d** | R9A 移交(去向写「R9C 或立即」),R9B 已取证 | **改判:维持 ■,但移交项给的修法不足以修好它**;正确修法已在仓库内,实测有效 |
| **H-R9B-a** | R9B 移交(「R9C/R9D 任一」) | **关闭并改述**:病因不是「抄了一份」,而是**守卫装在了没漂的那两份上** |
| **H-R9B-b** | R9B 移交(「R9C/R9D 任一」) | **关闭**:唯一相关测试只钉尖括号那一支,已逐字取证 |
| **H-R9B-c** | R9B 移交(「R9C/R9D 任一」) | **关闭并加重**;剩余推定部分**在本项目内结构性不可解**,不再续转 |

---

## 1. H-R9A-a:维持 ■,但修法要改

### 1.1 现象复核(与移交项一致)

判据是一个**不看主机**的子串测试。

`gateway/relay/media.py:92-94 @ 863e313`

```python
    def is_relay_media_url(self, url: str) -> bool:
        """Is ``url`` a connector re-host reference (needs our bearer to GET)?"""
        return "/relay/media/" in (url or "")
```

判为真就挂上网关 bearer 并直接 `urlopen` 出去。

`gateway/relay/media.py:162-174 @ 863e313`

```python
        if not url:
            return None
        needs_auth = self.is_relay_media_url(url)
        if needs_auth and not self.enabled:
            return None
        headers = {}
        if needs_auth:
            headers["Authorization"] = f"Bearer {self._bearer()}"

        def _get() -> Optional[str]:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
```

而 `url` 来自 relay 帧原始载荷,中间**没有任何校验**——`raw.get(...)` 直接落进事件字段。

`gateway/relay/ws_transport.py:268 @ 863e313`

```python
        media_urls=raw.get("media_urls") or [],
```

**bearer 是什么**:`make_upgrade_token(gateway_id, secret, ttl=…)`,即 `base64url(gateway_id:exp:HMAC)`,默认 TTL 300 秒。

`gateway/relay/auth.py:48 @ 863e313`

```python
_DEFAULT_UPGRADE_TTL_SECONDS = 300
```

拿到它的一方可在 5 分钟内**冒充该网关**完成 relay 的 WS upgrade。不是长期密钥,但也不是无害串。

### 1.2 改判的依据:移交项给的修法**堵不住**

R9A / R9B 两轮给的修法都是「比对配置的 connector host / `self._base_url`,而非放宽或收紧子串」。**这条修法必要,但不充分。**

原因是同一段代码用的是 `urllib.request.urlopen`,它**默认跟随重定向,且把 `Authorization` 原样带到新主机**。于是一个**主机完全合法**的 `{connector}/relay/media/{id}` 引用,只要对端回一个 302,bearer 就到了别处——主机校验对此**判通过**。

实验:`RelayMediaClient` 的 `_base_url` 与被请求 URL 主机**完全相同**(故建议的主机校验必然通过),重定向目标换到另一个本地端口 / 另一个主机名。

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  /home/user/hermes-venv/bin/python /path/to/redirect_probe2.py
```

```text
[同主机名换端口]
  URL 通过主机校验(建议修法)= True
  302 目标                    = http://127.0.0.1:59303/loot
  受害端收到 Host             = 127.0.0.1:59303
  受害端收到 Authorization    = True
  落盘内容来自受害端          = True  (b'stolen-response-body')
[换主机名 localhost]
  URL 通过主机校验(建议修法)= True
  302 目标                    = http://localhost:59303/loot
  受害端收到 Host             = localhost:59303
  受害端收到 Authorization    = True
  落盘内容来自受害端          = True  (b'stolen-response-body')
```

两个对照都泄漏,且**落盘内容来自跳转目标**——说明 302 被完整跟随、响应体被当作媒体收下。
本容器 Python 3.11.15。

### 1.3 正确修法已在仓库里,且实测有效

仓库自带一个**专为这个问题写的**处理器,连类名带 docstring 都对得上。

`hermes_cli/urllib_security.py:31-32 @ 863e313`

```python
class SafeCredentialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Preserve request headers only while redirects stay on one origin."""
```

它按 origin 归一化比对,跨 origin 时按**白名单**剥头(而不是猜哪个头名叫凭据),并先让 urllib 处理 307/308 语义。

`hermes_cli/urllib_security.py:45-58 @ 863e313`

```python
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Let urllib enforce status/method semantics first (notably 307/308).
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None

        resolved_url = urllib.parse.urljoin(req.full_url, newurl)
        if url_origin(resolved_url) != self._original_origin:
            # Use an allowlist rather than guessing credential header names.
            # normalize_extra_headers permits arbitrary secret-bearing names.
            for name, _value in list(redirected.header_items()):
                if name.lower() not in self._cross_origin_safe_headers:
                    redirected.remove_header(name)
        return redirected
```

对照实验(同一个 bearer、同一个 header 名、同一个 302):

```text
对照组 基线现状 urlopen()          -> 受害端收到 Authorization = True
实验组 open_credentialed_url()     -> 受害端收到 Authorization = False
```

**这道防线只装在 4 个调用点**,relay media 不在其中。

```verify
cd /home/user/hermes-agent && grep -rn "urllib_security" --include=*.py . \
  | grep -v "^./hermes_cli/urllib_security.py" | grep -v "^./tests/"
```

```text
./providers/base.py:218:        from hermes_cli.urllib_security import open_credentialed_url
./hermes_cli/azure_detect.py:49:from hermes_cli.urllib_security import open_credentialed_url
./hermes_cli/models.py:25:from hermes_cli.urllib_security import open_credentialed_url
./plugins/model-providers/anthropic/__init__.py:7:from hermes_cli.urllib_security import open_credentialed_url
```

四处全是**模型 provider** 路径。带网关冒充 bearer 的 relay media 路径没有。
这与 R9B 对 H-R9A-d 的判词是同一句:**不是没想到,是只装了一侧。**

### 1.4 为什么测试是绿的:第四份副本

同一个子串判断在全仓有 **4 份**,其中一份在**测试替身里**。

```verify
cd /home/user/hermes-agent && grep -rn '"/relay/media/"' --include=*.py .
```

```text
./gateway/relay/media.py:94:        return "/relay/media/" in (url or "")
./gateway/relay/adapter.py:471:                    if "/relay/media/" not in url:
./gateway/relay/adapter.py:477:                elif "/relay/media/" not in url:
./tests/gateway/relay/test_relay_media.py:73:        return "/relay/media/" in (url or "")
```

`adapter.py` 的两份是**就地内联**的,并未调用 `is_relay_media_url`:

`gateway/relay/adapter.py:469-479 @ 863e313`

```python
                if client is None:
                    # No authenticated client: keep public URLs, drop re-hosts.
                    if "/relay/media/" not in url:
                        localized.append(url)
                    continue
                path = await client.download(url)
                if path:
                    localized.append(path)
                elif "/relay/media/" not in url:
                    # A public URL that failed to download still has value as
                    # a URL (native adapters pass URLs to vision in some
```

而测试桩**自己重抄了一遍同一个谓词**:

`tests/gateway/relay/test_relay_media.py:72-73 @ 863e313`

```python
    def is_relay_media_url(self, url: str) -> bool:
        return "/relay/media/" in (url or "")
```

**测试替身复制了被测逻辑,于是这条判据实际上没有被任何测试验证过。** 换成主机校验版本后,这个替身仍会返回旧行为,测试照绿——修的时候必须连它一起改。

### 1.5 本轮的处置结论

- **维持 ■,不降级。** 判据 host-blind 属实,URL 未经校验属实,bearer 是网关冒充凭据属实。
- **修法改述**(这是本轮相对 R9A / R9B 的增量):
  1. `is_relay_media_url` 改为比对 `self._base_url` 的 **origin**(scheme+host+port),不是子串、也不只是 host;
  2. **同时**把 `download` / `upload` 的 `urlopen` 换成 `hermes_cli.urllib_security.open_credentialed_url`——只做第 1 步,1.2 的实验证明 bearer 仍会泄漏;
  3. `adapter.py:471` / `:477` 两处内联副本改为调用同一方法;
  4. `tests/gateway/relay/test_relay_media.py:72-73` 的替身必须跟着改,否则测试对修复无感。
- **仍然是推定的那一半,以及为什么它只能是推定**:R9B 标注「终端用户可直接触发」未取证。本轮给出该推定**不可在本仓库内消解**的理由——决定 `media_urls` 里能放什么的是 connector(relay 服务端),**它不在本仓库**;本仓库侧能确证的上界是「**能在入站帧里放 `media_urls` 的一方**可以触发」。
  代码自己的 docstring 承认这个列表里会有非 connector 的 URL。

  `gateway/relay/adapter.py:446-449 @ 863e313`

  ```python
      async def _localize_inbound_media(self, event) -> None:
          """Download connector re-hosted attachments to local temp paths.

          The wire's ``media_urls`` name connector re-hosts
  ```

  紧接的下一句是 "(``{connector}/relay/media/{id}``, per-gateway-bearer-authenticated) or
  public platform CDN URLs (Discord pass-through)"。这使「非 connector 主机会进入这个列表」
  从推测变成设计意图,但**具体哪个平台的哪个字段可被终端用户控制,仍在仓库外**。
- **去向**:不再续转为「待查」。作为**已定案**的 ■ 写入 R9C 报告与成品章。

### 1.6 把单点扩成人口统计:这道防线在全仓覆盖了多少

H-R9A-a 只是一个点。主线顺手做了全仓普查,想知道**「有防线但没装」是孤例还是常态**。

判定写死在脚本里,不 import 不执行:搜索面 = 基线全部 `.py` 共 3,846 个(排除 `.git`/`__pycache__`/
`node_modules`/`.venv`),AST 解析成功 3,846 / 失败 0。「凭据出网点」= 同一个函数体内**同时**出现
字符串常量 `"Authorization"` 与一处 stdlib 发送调用(`urlopen` / `opener.open` / `open_credentialed_url`)。

| 组 | 含义 | 非测试处数 |
|---|---|---|
| **A1** | 既不走公共防线,文件内也无任何禁跳转构造 | **19** |
| **A2** | 不走公共防线,但文件内自带禁跳转构造 | **4**(全部在 `scripts/ci/live_comment.py`) |
| **B** | 走 `open_credentialed_url` 公共防线 | **2** |
| C | 自拼 `Authorization` 但走 httpx / requests / aiohttp(另一套重定向语义) | 67(单独计数,不并入上面) |

即 **25 个 stdlib 凭据出网点里,只有 2 个用了那个专为此写的模块**;4 个各自造了轮子;19 个什么都没有。
`gateway/relay/media.py` 的 `upload()`(:96)与 `download()`(:154)**两处都在 A1**。

**这 19 处不等于 19 个可利用缺陷,必须说清楚**:绝大多数的 URL 来自硬编码常量或运营者配置,
攻击者碰不到,少一道跨 origin 剥头只是纵深不足。`gateway/relay/media.py` 之所以单独成 ■,
是因为**只有它的 URL 直接来自入站帧**(§1.1 的 `gateway/relay/ws_transport.py:268`)。
普查的意义在另一头:**它说明 §1.3 那个「不是没想到,是只装了一侧」不是偶然,而是这个仓库的默认状态——
公共防线写好了、测试齐全、`__all__` 导出了,然后 25 个同型调用点里接了 2 个。**

*本普查自身的一处修正(留痕):初版把「发送点」只定义为 `urlopen` / `opener.open`,
于是**走防线的函数根本不算发送点**,B 组被系统性少算,首次跑出的是 1 而不是 2。
把 `open_credentialed_url` 补进发送点定义后重跑得到上表。
一个把"合规写法"排除在分母外的普查,会让覆盖率看起来比实际更差。*

---

## 2. H-R9B-a:关闭,但病因要改述

移交项写的是:「同一份内置 STT 名单全仓三份、漂了一份;修法是 import 权威集合而非再抄一遍」。
**三份属实;但「作者不知道抄名单危险」不属实——恰恰相反。**

### 2.1 三份副本

第三份(漂掉的那份)只有 7 个名字,缺 `deepinfra`:

`tools/voice_mode.py:2193-2201 @ 863e313`

```python
    native_stt_available = stt_provider in {
        "local",
        "local_command",
        "groq",
        "openai",
        "mistral",
        "xai",
        "elevenlabs",
    }
```

另外两份各 8 个名字、**逐字相同**(连元素顺序都一样,只有变量名不同)。

`agent/transcription_registry.py:40-49 @ 863e313`

```python
_BUILTIN_NAMES = frozenset({
    "local",
    "local_command",
    "groq",
    "openai",
    "mistral",
    "xai",
    "elevenlabs",
    "deepinfra",
})
```

`tools/transcription_tools.py:341-350 @ 863e313`

```python
BUILTIN_STT_PROVIDERS = frozenset({
    "local",
    "local_command",
    "groq",
    "openai",
    "mistral",
    "xai",
    "elevenlabs",
    "deepinfra",
})
```

### 2.2 关键发现:守卫存在,只是没装在漂掉的那份上

作者**明确知道**这是复制,并在注释里写了依赖一个回归测试:

`tools/transcription_tools.py:336-337 @ 863e313`

```python
# Kept in sync with ``agent.transcription_registry._BUILTIN_NAMES`` —
# a regression test fails if they drift. The plugin hook from
```

该回归测试确实存在,而且写得很好(漂移时直接打印两侧差集):

`tests/agent/test_transcription_registry.py:176-183 @ 863e313`

```python
    def test_registry_builtins_match_dispatcher_builtins(self):
        from tools.transcription_tools import BUILTIN_STT_PROVIDERS

        assert transcription_registry._BUILTIN_NAMES == BUILTIN_STT_PROVIDERS, (
            "agent.transcription_registry._BUILTIN_NAMES and "
            "tools.transcription_tools.BUILTIN_STT_PROVIDERS have drifted!\n"
            f"  Registry only: {sorted(transcription_registry._BUILTIN_NAMES - BUILTIN_STT_PROVIDERS)}\n"
            f"  Dispatcher only: {sorted(BUILTIN_STT_PROVIDERS - transcription_registry._BUILTIN_NAMES)}\n"
```

TTS 侧有一份**完全同型**的钉住测试——连断言结构都一样,只换了两个名字:

`tests/agent/test_tts_registry.py:209-212 @ 863e313`

```python
        from tools.tts_tool import BUILTIN_TTS_PROVIDERS

        assert tts_registry._BUILTIN_NAMES == BUILTIN_TTS_PROVIDERS, (
            "agent.tts_registry._BUILTIN_NAMES and "
```

两者本轮实跑通过:

```verify
cd /home/user/hermes-agent && HERMES_DISABLE_LAZY_INSTALLS=1 \
  HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/agent/test_transcription_registry.py tests/agent/test_tts_registry.py \
  tests/tools/test_tts_xai_speech_tags.py
```

```text
=== Summary: 3 files, 49 tests passed, 0 failed (100% complete) in 2.0s (8 workers) ===
```

而第三份副本**零测试覆盖**:

```verify
cd /home/user/hermes-agent && grep -rn "native_stt_available" tests/ --include=*.py
```

```text
(无输出,退出码 1)
```

*(阳性对照见 §4:同一条 grep 在非测试目录能命中 3 处,故零命中为真而非命令写错。)*

### 2.3 改述后的结论

**守卫钉住的是「注册表 ↔ 分派器」这一对——两份都没漂;漂的是第三份,一个 UI 面的能力探测,不在任何人想到的"那一对"里。**
这比「应该 import 而不是抄」更准确,也更可迁移:**当一份知识必须有副本时,危险的不是副本数,而是"谁被算进了守卫的作用域"。** 守卫本身没失效,是作用域画小了。

### 2.4 顺带查:全仓还有多少处同型硬编码名单

移交项要求的普查。用 AST 扫描,不 import 不执行。判定规则写死在脚本里(见报告)。
**两个读数口径不同,不是同一指标的两次测量**:

| 口径 | 权威名单认定 | 停用表 | 非测试命中 | 测试命中 |
|---|---|---|---|---|
| 宽 | ALL_CAPS 名含 PROVIDER/BACKEND/MODEL/ENGINE/VENDOR | 无 | **100 处**(未按 文件:行 去重) | 44 处 |
| 严 | ALL_CAPS 名含 PROVIDER | 有(剔除 `api_key`/`base_url` 等配置键) | **58 处**(已去重) | 21 处 |

宽口径把 `PROVIDER_FIELDS` 一类**配置键**名单也算了进来,严口径剔除。**报告采信严口径的 58。**
搜索面:基线全部 `.py` 共 3,846 个文件,AST 解析成功 3,846 / 失败 0(含 `tests/`,分开计数)。

严口径下密度最高的两处样本(各摘前 3 行):

`hermes_cli/main.py:10586-10588 @ 863e313`

```python
        return [
            "auto", "openrouter", "nous", "openai-codex", "xai-oauth", "copilot-acp", "copilot",
            "anthropic", "gemini", "vertex", "xai", "bedrock", "azure-foundry",
```

`agent/coding_context.py:179-181 @ 863e313`

```python
        ("claude", "sonnet", "opus", "haiku",
         "gemini", "gemma", "deepseek", "qwen", "kimi", "glm", "grok",
         "hermes", "llama", "mistral", "devstral", "minimax"),
```

另有 `hermes_cli/models.py:442`(51 名)、`hermes_cli/main.py:3463`(20 名)。
**这些都没有 §2.2 那种钉住测试**——即 H-R9B-a 的形态在全仓至少还有 58 个落点,守卫只装了 2 个(STT 一对、TTS 一对)。

---

## 3. H-R9B-b:关闭

移交项:「包裹型标签只认尖括号而提示词禁止尖括号;现有测试只钉住尖括号那一支,故一直是绿的」。
R9B 已实跑正/反例。本轮补的是**「测试只钉一支」这半句的逐字取证**。

搜索面:`tests/` 全目录 `*.py`,模式 `whisper]|whisper>|_XAI_SPEECH_TAG_RE`,**全仓仅 1 处命中**:

`tests/tools/test_tts_xai_speech_tags.py:25 @ 863e313`

```python
    text = "Bonjour. [pause] <whisper>Déjà balisé.</whisper>"
```

唯一的语料用的是**尖括号** `<whisper>…</whisper>`——正是正则认得的那一支;提示词强制的方括号形态
`[whisper]…[/whisper]` 在整个测试目录里**没有任何用例**。移交项成立,**关闭**。

---

## 4. H-R9B-c:关闭并加重

移交项:「schema 承诺可传本地绝对路径,默认后端 FAL 原样透传不读文件;『FAL 会拒绝文件路径』是推定,未发真请求」。

**加重的部分**:不只是 FAL 这一个后端不读文件——**整个 `tools/image_generation_tool.py` 里没有任何一处读本地文件**。
搜索面:该单文件,模式 `read_bytes|open\(|b64encode|Path\(|os\.path\.(exists|isfile)|data:image`,命中 **0**。

```verify
cd /home/user/hermes-agent && grep -nE "read_bytes|open\(|b64encode|Path\(|os\.path\.(exists|isfile)|data:image" tools/image_generation_tool.py; echo "退出码=$?"
```

```text
退出码=1
```

零命中的 grep 是本项目明令要防的形状,故给**三项阳性对照**证明命令没写错:

```verify
cd /home/user/hermes-agent && ls -l tools/image_generation_tool.py \
  && grep -cE "image_urls|def " tools/image_generation_tool.py \
  && grep -cE "read_bytes|open\(|b64encode|Path\(|os\.path\.(exists|isfile)|data:image" gateway/relay/media.py
```

```text
-rw-r--r-- 1 root root 65414 Aug  9 05:34 tools/image_generation_tool.py
67
6
```

文件存在且非空(65 KB);另一模式在**同一文件**命中 67 处;**同一模式**在别的文件命中 6 处。故零命中为真。

**结论**:schema 对模型承诺的「本地绝对路径」在该模块内**没有任何后端能兑现**,不是 FAL 一家的问题。■ 成立并加重。

**剩余推定部分的处置**:「FAL 收到文件路径后是拒绝、还是静默产出错图」需要真实付费凭据发一次请求。
本项目边界明写「不配置任何付费凭据」,故这一半**在本项目内结构性不可解**。
**不再作为待查项续转**——它不是"还没做",是"按项目边界做不了"。写进报告的待提供项。
