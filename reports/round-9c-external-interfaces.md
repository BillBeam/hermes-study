# R9C · 对外接驳面 —— 传输、凭据、计费与可观测性

**一句话结论**:防线不缺,缺的是把它装到第二处。

本轮读完台账 `round=R9C` 的 **47 文件 / 19,274 行**(开工先核,与任务书一致),
切六片派工;结清 R9A / R9B 移交中归属本轮的全部条目,其中 **H-R9A-a 给出处置结论**;
给出 **L1 全量 deep-read 的剩余判定与 R9D 收口确认条件**。

---

## 1. 开工先核范围

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$5); if($5=="R9C"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
47 文件 / 19274 行
```

47 个全部 `layer=L1`、`status=R1-inventoried`(从未开工)。拆片见
`notes/r9c-01-scope-and-l1-closeout.md` §1.1:A Codex 传输族 4 / B 传输层契约 7 /
C 中继与插件 LLM 5 / D 密钥来源 8 / E 可观测性与外发 13 / F 计费与 HTTP 客户端 10,合计 47。

### 1.1 开工杂项:惰性安装纪律(为本轮的 venv 口径服务)

基线的可选依赖是**惰性安装**的:导入某后端时若缺包,它会**联网 pip 安装**到当前 venv
(默认开启)。R9B 已记下这条(H-R9B-g:"一个『读代码』的动作可以产生网络副作用并改变自身运行环境"),
本轮开工先把它关掉,并**实测**开关有效而不是照文档假定:

```text
HERMES_DISABLE_LAZY_INSTALLS = 1
HERMES_LAZY_INSTALL_TARGET  = None
_lazy_install_target()      = None
_allow_lazy_installs()      = False
--- 对照:不设该变量 ---
_allow_lazy_installs()      = True
```

此后所有跑基线代码的命令一律带 `HERMES_DISABLE_LAZY_INSTALLS=1`,并写进六份派工书。

---

## 2. 台账报数

```verify
cd /home/user/hermes-study && python3 scripts/verify_ledger.py /home/user/hermes-agent data/ledger.tsv
```

```text
OK baseline=863e31318 files=8530 total_lines=2608452
  L1: files=563 lines=522207
  L2: files=2131 lines=671639
  L3: files=1895 lines=602085
  L4: files=560 lines=55902
  LT: files=3381 lines=756619
  SUM == repo total: 2608452
```

五层加总 = 全仓总行数 **2,608,452**,守恒成立;基线 HEAD 仍是 `863e31318`,工作区干净。
47 个文件的 `status` 全部转为 `R9C-deep-read`(转前 47 个 `R1-inventoried`,转后 0 个)。

**恢复必报项 —— `R1-inventoried` 剩余**:

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{sub(/\r$/,"",$6); if($6=="R1-inventoried"){n++; l+=$3}} \
    END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

```text
7785 文件 / 1988790 行
```

(开工时为 7,832 文件 / 2,008,064 行,差额正好是本轮的 47 文件 / 19,274 行。)

---

## 3. L1 全量 deep-read 的剩余判定(验收项 ②)

**R9D 是 L1 的最后一片。** L1 合计 563 文件 / 522,207 行,已完成 467 文件 / 476,499 行,
剩 96 文件 / 45,708 行,**全部落在 R9C(47 / 19,274)与 R9D(49 / 26,434)两轮,没有第三轮**。
本轮复核 R9B "由三轮改两轮" 的判定成立,不再变更。R9C 收工后 L1 只余 R9D 那 49 个文件。

### 3.1 一条实测:只看 status 列不足以证明"读完了"

把已标 `*-deep-read` 的 **467** 个 L1 文件路径,拿去产出语料里做精确子串搜索。
**下面两行是不同语料下的两次独立测量,不是同一读数的两种写法:**

| 语料 | 全路径零命中 | 连裸文件名也零命中 |
|---|---|---|
| `notes/` + `chapters/` | 42 文件 / 8,234 行 | 14 文件 / 5,150 行 |
| `notes/` + `chapters/` + `reports/` | **40 文件 / 7,811 行** | **11 文件 / 2,820 行** |

采信下面一行(语料最全,对既有产出最宽容)。即:467 个"已 deep-read"里,
**40 个文件的路径在全部产出里一次也没出现过**,其中 **11 个连裸文件名都搜不到**。

**限定说清楚**:"路径没出现"不等于"没读过"——底稿理论上可以描述一个文件而不写它的路径。
但本项目的证据格式要求断言紧跟 `路径:行号`,所以**路径零命中意味着该文件上没有任何一条可溯源断言**。
足以说明 status 列在这 40 个文件上高于实际交付。**这是历史积压,不是本轮造成的。**

### 3.2 R9D 收口确认条件(收口那轮要报数哪些项)

前四项为硬条件,缺一不可。完整版见 `notes/r9c-01-scope-and-l1-closeout.md` §3.3。

1. **台账归零**:`layer=L1 && status=R1-inventoried` = **0 文件 / 0 行**;
   L1 各 `*-deep-read` 加总 = **563 文件 / 522,207 行**。
2. **分层未被搬动**:收口时 L1 的**文件集合**与 R9C 收工时逐行 diff,增减必须为 0。
   *理由:达成"L1 全读完"最省力的办法不是去读,而是把读不动的文件降层到 L2;
   只报 status 列的话,这种搬动完全不可见。*
3. **守恒仍成立**:`verify_ledger.py` 通过,五层加总 = 2,608,452,基线工作区干净。
4. **点名覆盖率**:对全部 563 个 L1 文件跑 §3.1 那个搜索,报出全路径零命中数与裸文件名零命中数。
   R9D 新增的 49 个必须是 **0 / 0**;历史积压的 40 / 11 若不清,**必须点名列出并指明归哪轮补**,
   不得以"L1 已收口"的名义掩盖。
5. **关卡**:定稿全量零 MISMATCH / 零 BLOCK-DRIFT / 零 TABLE-DRIFT / 零 TABLE-OUT-OF-RANGE,
   退出码 0;当轮 notes 口径可校验比例 ≥70%。
6. **对 R12 的宣告**:H-R8D-i 把 R12 前置定为"L1 全部 deep-read"。收口轮须**显式宣告**是否满足;
   满足则同时给出 R12 待装订的成品章清单(届时 17 章),不满足则给补齐计划。

---

## 4. H-R9A-a 的处置结论(验收项 ①)

移交时去向写的是「R9C 或立即」,本轮给出**处置结论:维持 ■ 不降级,但推翻移交项给的修法**。
完整取证见 `notes/r9c-90-handover-rulings.md` §1。

### 4.1 现象复核(与移交项一致)

判据是不看主机的子串测试:

`gateway/relay/media.py:92-94 @ 863e313`

```python
    def is_relay_media_url(self, url: str) -> bool:
        """Is ``url`` a connector re-host reference (needs our bearer to GET)?"""
        return "/relay/media/" in (url or "")
```

URL 来自 relay 帧原始载荷,中间零校验:

`gateway/relay/ws_transport.py:268 @ 863e313`

```python
        media_urls=raw.get("media_urls") or [],
```

bearer 是 300 秒 TTL 的网关冒充令牌(`gateway/relay/auth.py:48` 的
`_DEFAULT_UPGRADE_TTL_SECONDS = 300`)。

### 4.2 改判点:移交项给的修法堵不住

R9A / R9B 两轮给的修法都是"比对配置的 connector host / `self._base_url`"。
**必要,但不充分。** 同一段代码用 `urllib.request.urlopen`,它默认跟随重定向、
**把 `Authorization` 原样带到新主机**。实验里被请求 URL 的主机与 `self._base_url` **完全相同**
(故建议的主机校验必然判通过):

```text
[同主机名换端口]
  URL 通过主机校验(建议修法)= True
  受害端收到 Authorization    = True
  落盘内容来自受害端          = True  (b'stolen-response-body')
[换主机名 localhost]
  URL 通过主机校验(建议修法)= True
  受害端收到 Authorization    = True
  落盘内容来自受害端          = True  (b'stolen-response-body')
```

### 4.3 正确修法已在仓库里,实测有效

`hermes_cli/urllib_security.py:31-32` 的 `SafeCredentialRedirectHandler`
按 origin 归一化 + 头白名单剥离,并先让 urllib 处理 307/308 语义。对照实验:

```text
对照组 基线现状 urlopen()          -> 受害端收到 Authorization = True
实验组 open_credentialed_url()     -> 受害端收到 Authorization = False
```

### 4.4 测试为什么两轮全绿:第四份副本在测试替身里

```verify
cd /home/user/hermes-agent && grep -rn '"/relay/media/"' --include=*.py .
```

```text
./gateway/relay/media.py:94:        return "/relay/media/" in (url or "")
./gateway/relay/adapter.py:471:                    if "/relay/media/" not in url:
./gateway/relay/adapter.py:477:                elif "/relay/media/" not in url:
./tests/gateway/relay/test_relay_media.py:73:        return "/relay/media/" in (url or "")
```

**测试替身重抄了被测谓词**,所以这条判据从未被任何测试验证过。修的时候必须连它一起改。

### 4.5 处置结论

- **维持 ■**,不降级。
- **修法四步**:(1) 改为比对 `self._base_url` 的 **origin**;(2) **同时**把 `urlopen` 换成
  `open_credentialed_url`——只做第 1 步实测仍泄漏;(3) `adapter.py:471`/`:477` 两处内联副本
  改为调用同一方法;(4) 测试替身必须跟着改。
- **仍是推定的那一半,及其不可消解的理由**:R9B 标注"终端用户可直接触发"未取证。
  本轮给出该推定**不可在本仓库内消解**的理由——决定 `media_urls` 里能放什么的是 connector
  (relay 服务端),**它不在本仓库**;仓库侧能确证的上界是"能在入站帧里放 `media_urls` 的一方可以触发"。
- **不再续转为待查**,作为已定案 ■ 写入成品章。

### 4.6 顺带:把单点扩成人口统计

搜索面 = 基线全部 3,846 个 `.py`(AST 解析成功 3,846 / 失败 0)。
「凭据出网点」= 同一函数体内同时出现字符串常量 `"Authorization"` 与一处 stdlib 发送调用。

| 组 | 含义 | 非测试处数 |
|---|---|---|
| A1 | 既不走公共防线,文件内也无禁跳转构造 | **19** |
| A2 | 不走公共防线,但文件内自带禁跳转构造 | **4** |
| B | 走 `open_credentialed_url` 公共防线 | **2** |
| C | 自拼 `Authorization` 但走 httpx / requests / aiohttp | 67(另一套语义,单独计数) |

**25 个 stdlib 凭据出网点里只有 2 个接了那个专为此写的模块。**
说清楚:这 19 处不等于 19 个可利用缺陷——多数 URL 来自硬编码常量或运营者配置,攻击者碰不到;
`gateway/relay/media.py` 单独成 ■ 是因为**只有它的 URL 直接来自入站帧**。

*本普查自身的一处修正(留痕):初版把"发送点"只定义为 `urlopen`/`opener.open`,
于是走防线的函数根本不算发送点,B 组被系统性少算,首跑得 1 而非 2。补入
`open_credentialed_url` 后重跑得上表。一个把合规写法排除在分母外的普查,会让覆盖率显得比实际更差。*

---

## 5. 其余移交项结清

| 移交项 | 结论 |
|---|---|
| **H-R9B-a**(STT 名单三份漂一份) | **关闭并改述** |
| **H-R9B-b**(xAI 语音标签只认尖括号) | **关闭** |
| **H-R9B-c**(image schema 承诺本地路径) | **关闭并加重**;剩余推定判为本项目内结构性不可解 |

**H-R9B-a 的改述**:移交项说"病因是抄了一份,修法是 import 权威集合"。**不准确。**
仓库**明确知道**这是复制(`tools/transcription_tools.py:336-337` 注释写着
"a regression test fails if they drift"),而且那个回归测试确实存在、写得很好、本轮实跑通过。
**漂的是第三份**——`tools/voice_mode.py:2193` 一个 UI 侧能力探测,**零测试覆盖**
(`grep -rn "native_stt_available" tests/` 无输出)。
**守卫没失效,是守卫的作用域画小了。** 真正该管理的是"哪些副本进了钉住表"。

顺带普查(移交项要求):同型就地硬编码名单,**严口径 58 处**(已按 文件:行 去重),
另有宽口径 100 处(未去重、含配置键名单)——**两个口径定义不同,不是同一指标的两次测量**,
报告采信 58。搜索面为基线全部 3,846 个 `.py`。而钉住测试全仓只装了 2 处。

**H-R9B-c 的加重**:不只 FAL 一个后端不读文件——**整个 `tools/image_generation_tool.py` 里
没有任何一处读本地文件**(该单文件模式零命中,已给三项阳性对照证明命令没写错)。
schema 承诺的"本地绝对路径"在该模块内**没有任何后端能兑现**。
剩余的"FAL 收到路径后是拒绝还是产出错图"需要真实付费凭据,项目边界明写不配置,
故**结构性不可解,不再续转**,列入 §9 待提供项。

---

## 6. 定案

### 6.1 记号报数

六片底稿合计 **81 条**:**■ 37 / ▲ 12 / ◇ 28 / ◎ 4**(逐条带锚点,在各片底稿的发现清单)。
主线另定案 4 条移交项。

| 片 | ■ | ▲ | ◇ | ◎ | 小计 |
|---|---|---|---|---|---|
| A Codex 传输族 | 5 | 2 | 3 | 1 | 11 |
| B 传输层契约 | 6 | 2 | 10 | 1 | 19 |
| C 中继与插件 LLM | 5 | 1 | 2 | 1 | 9 |
| D 密钥来源 | 6 | 3 | 4 | 0 | 13 |
| E 可观测性与外发 | 7 | 3 | 6 | 1 | 17 |
| F 计费与 HTTP 客户端 | 8 | 1 | 3 | 0 | 12 |
| **合计** | **37** | **12** | **28** | **4** | **81** |

**D 片明确报 ◎ = 0 并说明"逐条核过各文档可量化断言,没有该形态,不凑数"**,按原样采信。

### 6.2 主线实跑复核的七条(不照抄底稿)

| # | 条目 | 主线复核方式与结果 |
|---|---|---|
| 1 | H-R9A-a 全链 | 三个本地实验:302 泄漏、主机校验判通过、公共防线有效(True→False) |
| 2 | A ■-1 `codex_app_server_session.py:619` | 重跑复现:无审批 0.00s / 排空后 3.00s 空转;最坏一档错因被替换成 `'turn timed out after 3.0s'` 且触发会话退休 |
| 3 | B ■-1 `chat_completion_helpers.py:2172` | 静态对读:传输侧 3 处处理 `effect_disposition`,摘要路径副本 0 处,而副本注释自称 "mirror that sanitization here" |
| 4 | B ■-6 `transports/__init__.py:53` | 实跑:`get_transport('anthropic')` 返回 `None`,契约方法直接 `AttributeError` |
| 5 | F ■-1 `microsoft_graph_client.py:139` | MockTransport 实跑:令牌被发往响应体指定的 `http://attacker.example`,且第二页真的被取回 |
| 6 | F ■-2 `billing_usage.py:270` | 实跑:主开关关闭下 `credits_tracker` 返回 `None`(守卫生效),`billing_usage` 造出完整 `status='depleted'` / 已花 $20 假账,推翻其 docstring 的 "can never" |
| 7 | E ▲-2 出站 webhook 载荷 | 静态全链:`_TOP_LEVEL_PAYLOAD_KEYS` 仅四键、`result` 不在其中 → 完整工具输出逐字进 `extra`;文档只说 "tool inputs and event metadata" |
| 8 | D ■-1 `op_cache.json` | 全仓对读:`bws_cache` 出现在 **4 个守卫点**,`op_cache` 出现在 **0 个**;而 `file_safety.py:281-283` 的注释正记着 Bitwarden 那次同样的疏漏 |

### 6.3 结构性结论

**本轮 37 条 ■ 里,数量最多的一类不是"没想到",而是"想到了、写好了、只装了一处"。**
至少五次同形重演,每次标的不同:

| 防线 | 装了 | 没装 |
|---|---|---|
| 跨 origin 剥凭据头(`urllib_security`) | 2 个调用点 | 另外 23 个 |
| 副本漂移钉住测试 | 注册表↔分派器那一对(没漂) | UI 侧第三份(漂了) |
| 夹具双钥匙守卫 | `credits_tracker` | `billing_usage` |
| 明文密钥缓存读禁清单 | `bws_cache.json`(4 处) | `op_cache.json`(0 处) |
| 主循环的终止条件 | 主循环 | 审批前置排空副本 |

**可迁移的结论**:一个安全模块的**存在**不是覆盖率的证据。
写完防线要同时写一条能数出"应该用它的地方有几个、实际用了几个"的检查——
本轮那条 23:2 就是这么数出来的,数完才知道问题不是孤例。

**一条反面对照**(同仓库内,B 片提供):`run_agent.py:7274` 一带是第三份同类清洗逻辑,
它**从传输层 import 谓词而不是重抄**,至今没漂。同仓库、同类逻辑——抄的两份都漂了,共享的没漂。

---

## 7. 关卡读数

| 范围 | citations | OK | 可校验比例 | 阻断项 |
|---|---|---|---|---|
| **当轮 notes(报告口径)** | 669 | 585 | **87.4%** | 0 |
| 定稿全量(chapters 全部 + 当轮 notes + 当轮 report) | 1,075 | 781 | 72.7% | 0 |
| 本轮成品章单独 | 18 | 17 | **94.4%** | 0 |

*(定稿全量那一行跑的是 CLAUDE.md 规定的范围 `chapters/*.md notes/r9c-*.md reports/round-9c-*.md`。
另跑过一次不含报告的 `chapters/*.md notes/r9c-*.md`,读数是 1,067 / 779 / 73.0% ——
**两行是不同文件集合上的两次测量,不是同一读数**,以规定范围那一行为准。)*

**0 MISMATCH / 0 BLOCK-DRIFT / 0 TABLE-DRIFT / 0 TABLE-OUT-OF-RANGE / 0 MISSING-FILE,
退出码 0,全程未用 `--fix`。** 台账关、首句关同绿。基线 `863e313` 全程干净
(每片交付后各断言一次 `git status --porcelain` 为空)。

六章 UNCHECKED ≥90% 的「疑似锚点排版不合规」提示照常打印,是 H-R8D-g 的已知欠账(归 R11B),**本轮未动**。

---

## 8. 测试(按 CLAUDE.md 连环境一起记)

| 片 | 文件 | passed | failed |
|---|---|---|---|
| A Codex 传输族 | 19 | 269 | 0 |
| B 传输层契约 | 13 | 212 | **1** |
| C 中继与插件 LLM | 10 | 230 | 0 |
| D 密钥来源 | 10 | 145 | 0 |
| E 可观测性与外发 | 11 | 68 | 0 |
| F 计费与 HTTP 客户端 | 23 | 198 | 0 |
| 主线(移交项取证) | 3 | 49 | 0 |
| **各片自报读数之和** | **89** | **1,171** | **1** |

**口径交代**:上面的合计是**各片自报读数之和**,主线**没有**另跑一次去重的合并全量,
故片间若有重复文件会被重复计入。这是一个求和,不是一次测量。

**唯一失败** `tests/agent/test_auxiliary_transport_autodetect.py::test_resolve_provider_client_kimi_coding_wraps_anthropic`:
**容器环境限制,非代码缺陷**。`anthropic` SDK 不在 `[dev]` extra,被测的探测逻辑**判定正确**
(认出 `api.kimi.com/coding` 说 Anthropic Messages),只是建客户端时 ImportError 后按设计回落
OpenAI wire。属 H-R8D-j / H-R9B-e 已知的那一类,且是"表现为普通断言失败而非收集期 ImportError"
的隐蔽形态。

**一条必须交代的静默跳过**:`tests/monitoring/test_otlp_exporter.py` 开头是
`pytest.importorskip("opentelemetry.sdk.trace")`,本容器没装 otlp extra,**整个文件一条没跑**。
所以 E 片的 "68 passed" **不覆盖** span 映射与 `_resolve_headers`。属容器环境限制。
CLAUDE.md 已知的 6 条必然失败用例,本轮范围内一条都没碰到。

**环境**:venv **开工 87 包 / 收工 87 包**,两次数法(`pip list` 去表头计数、
`site-packages/*.dist-info` 计数)在开工与收工**四个读数全部为 87**。
**本轮期间未发生任何安装**——`HERMES_DISABLE_LAZY_INSTALLS=1` 已在开工实测有效并写进六份派工书,
六片交付时均自报未装包,主线在每次收件时复核 venv 计数。Python 3.11.15。

---

## 9. 诚实申报

1. **主线的一次自我修正(普查口径)**:§4.6 的凭据出网普查初版把"发送点"只定义为
   `urlopen`/`opener.open`,**把合规写法排除在分母外**,B 组少算(首跑 1、实为 2)。已修正并留痕。
2. **主线的第二次自我修正(词表口径)**:§5 的硬编码名单普查初版词表混入了配置键
   (`api_key`/`base_url` 等),得 100 处;加停用表并去重后得 58 处。**两个数口径不同,已分别标注。**
3. **主线一次差点误判 D 片**:跑合并关卡时 `notes/r9c-*.md` 这个通配扫进了 D 片**正在写入**的底稿,
   报出 3 MISMATCH + 2 BLOCK-DRIFT。文件当时已有 167 条引用、看着像成品。
   按 CLAUDE.md「只以完成信号为准」**未做任何处置**;D 自己交付前已全部改正,复跑 95.3% 通过。
   **这正是那条规矩要防的形状,而这次它挡住了。**
4. **派工书两处措辞被子代理纠正**,已照实采纳:(a) C 片指出 `plugin_llm` 是**宿主把模型借给插件**,
   与我写的方向相反;(b) D 片指出 `tools/credential_files.py` **不是**"凭据落盘那一侧",
   它是远端沙箱的文件透传注册表,**一行落盘代码都没有**——真正的落盘侧在
   `hermes_cli/secrets_cli.py`,不在本轮范围内。
5. **一处子代理拒绝套用主线给的框架,按原样采信**:E 片明确判定它那三条外发通道
   **不属于** R9B 红线(端点全部来自本地 config,无一来自远端响应),并给出理由。
   我在派工书里点名让它去找同型点,它查完说"不是",这条按它的判断写进报告。
6. **一处子代理拒绝并案,按原样采信**:D 片认为 Bitwarden `server_url` 不校验 scheme 与 R9B 两条
   **不同型**(那两处 URL 不是用户直接书写的,这里是用户在向导里亲手填的自建服务器地址),
   记为设计缺口而非 ■。
7. **未取证部分**:各片底稿均设「未取证/推定」节,合计 30 余条,均带锚点。其中影响面最大的三条——
   (a) A 片**从未真跑过 `codex app-server`**(容器无该二进制、离线),app-server 行为全部来自读码 +
   注入假客户端;(b) F 片 ■-1 只证明了"若 nextLink 指向任意主机则令牌跟着走",
   **未**证明 Graph 现实中会返回异常主机的 nextLink;(c) E 片对 `huggingface_hub` 是否读
   `HF_ENDPOINT` 未取证(库未安装),只断言 hermes 侧不传 `endpoint=`。
8. **本轮未做的事**:未跑真实模型/计费/云端点,未配置任何凭据;`chapters/` 六章的 UNCHECKED 欠账未动。

---

## 10. 待提供项(不自行猜测或伪造)

| 项 | 用途 | 阻塞的结论 |
|---|---|---|
| FAL 付费凭据 | 向 FAL 发一次带本地路径的真实请求 | H-R9B-c 剩余推定("拒绝 / 静默产出错图")—— 按项目边界**不可解** |
| 真实 Nous Portal 账号 | 对读 `/usage` 两条路径的 wire 字段 | F ■-3 是"在线缺陷"还是"潜伏" |
| 可跑的 `codex` 二进制 + 凭据 | 真跑 app-server 协议 | A 片全部 app-server 行为断言的实证等级 |
| `[otlp]` / `[fal]` 等平台 extra | 让被 importorskip 跳过的用例真跑 | E 片 span 映射与 `_resolve_headers` 的覆盖 |

---

## 11. 移交清单(每条带锚点 + 一句话现象)

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R9C-a** | R9D 或 R11A | `hermes_cli/nous_billing.py:179` 的 `resolve_portal_base_url` | 读环境变量与存储的 `portal_base_url` 时**不查** `_NOUS_PORTAL_ALLOWED_HOSTS`,而返回值在 `:399-402` 被用作 `Authorization: Bearer` 的目的地;同仓库 `hermes_cli/auth.py:5900` 读同一存储字段时是查清单的。文件不在 R9C 的 47 个内,故未定案 |
| **H-R9C-b** | R9D | `hermes_cli/secrets_cli.py` 全文 | D 片指出真正的"凭据落盘那一侧"在这里(token 写 `.env`),本轮只按需读了两处;`tools/credential_files.py` 一行落盘代码都没有 |
| **H-R9C-c** | R11A | `agent/transports/__init__.py:53-56` 的 `except ImportError: pass` | 分不清"可选包没装"与"我们自己模块里的 import bug",两者都被吞掉、`get_transport` 静默返回 `None`;修法是检查 `exc.name` |
| **H-R9C-d** | R11 复盘 | `tests/gateway/relay/test_relay_media.py:72-73` 的替身 | 测试替身重抄被测谓词导致关卡长期空绿;值得做一次全仓普查:还有多少测试替身复制了被测逻辑而非接口 |
| **H-R9C-e** | R11B | 本报告 §3.1 的 40 / 11 | 已标 `*-deep-read` 但全语料零点名的历史积压,需指定补齐轮次 |
| **H-R8D-g**(续转) | R11B | `chapters/r2-*` 等六章 | 校验器逐章点名 UNCHECKED ≥90%;本轮全量 73.0%,**欠账未动** |
| **H-R8D-h**(续转) | R11 复盘 | `notes/r8d-str-setup-and-ux.md` 的两条 docstring 级 ▲ | 模块 docstring 级 ▲ 与"作者自绘地图"级 ▲ 是否分开计数,仍需统一裁定 |
| **H-R8D-i**(续转) | R12 前置 | 本报告 §3.2 | R12 前置条件更新为"再做完 R9D 一轮",并按 §3.2 六项确认 |
| **H-R8D-j / H-R9B-e**(续转) | R11A | `pyproject.toml` 的 extra 定义 | `pip install -e ".[dev]"` 装不出全绿套件;本轮新增一个形态:`importorskip` 导致**整文件静默不跑**而计数仍显示全绿 |
| **H-R9B-f / H-R9B-g**(续转) | R11 复盘 | 见 R9B 报告 §9 | 本轮已把 H-R9B-g 的纪律落地为开工杂项(实测开关有效),但"写进 CLAUDE.md"这一步仍待复盘轮裁定 |
| **H-R9A-b / c / e / f / g**(续转) | R9D | `reports/round-9a-capability-organization.md` §11 | R9A 移交、归 R9D 的五条,本轮未动 |

*(各片底稿另有 40 余条簇内移交项,均带锚点,留在各自底稿的移交节,不在本表重复。)*

---

## 12. 下一轮(R9D)建议

1. **范围**:台账 `round=R9D` 的 49 文件 / 26,434 行 —— **L1 的最后一片**。
2. **必须按 §3.2 的六项收口**,尤其第 2 项(分层未被搬动)与第 4 项(点名覆盖率)。
3. 落实 R9A 移交归 R9D 的五条(H-R9A-b / c / e / f / g)与本轮的 H-R9C-a / b。
4. 显式宣告 R12 前置是否满足。
