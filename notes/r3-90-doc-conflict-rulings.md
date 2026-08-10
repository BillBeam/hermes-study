# R3-90 文档-代码冲突定案(R3 工具基础设施范围)

> 基线 `863e31318`。对第一轮标记的 ▲(文档不符)与 ◇(文档未载)中**属于 R3 机制簇**的条目
> 逐条定案。R1 编号指 `reports/round-1-survey.md` §2.16 与能力点 ▲ 标记。

## A. 结论一览

| # | 条目(R1 出处) | 定案 | 证据 |
|---|---|---|---|
| 1 | security.md:101 hardline 与 `UNRECOVERABLE_BLOCKLIST` 同步(R1 §2.16-16) | **证伪(符号)+ 证实(机制)** | §B.1 |
| 2 | security.md:665 allow_private_urls 全放行(R1 §2.16-17) | **证实(文档过度声称)** | r3-10 §8.2 |
| 3 | security.md:654 DNS 失败 fail-closed(R1 §2.16-18) | **证实(需按代理条件修正)** | r3-10 §8.3 |
| 4 | tools-runtime.md:91 check_fn "cached per-call"(R1 §2.16-19) | **证实(实为 30s TTL + 60s 宽限)** | §B.2 |
| 5 | ◇ Schema 多后端清洗层 + property-key 往返(R1 2.5-3) | **证实(仅 Gemini-adapter 侧一句模糊提及)** | r3-20 定案 a |
| 6 | ◇ 三层工具输出限长与结果持久化(R1 2.5-5) | **修正(第一层已文档化;二三层未见)** | r3-20 定案 b |
| 7 | ◇ Tool Search 渐进披露(R1 2.5-10) | **证伪(有专门详尽的 tool-search.md)** | r3-20 定案 c |
| 8 | ◇ execute_code 编程式工具调用(R1 2.5-11) | **证实(README 属实但低估机制深度)** | r3-30 定案 C1 |
| 9 | ◇/▲ MCP 客户端侧安全与动态注册(R1 2.5-12) | **修正(命名/动态注册已文档化;7 项安全机制未见)** | r3-30 定案 C2 |
| 10 | ◇ 分层命令审批体系(R1 2.5-6) | **修正(security.md 讲了机制但符号名错、边界条件漏)** | §B.1 + r3-10 §1 |

另有 **2 处源码内注释/docstring 漂移(R3 新发现)**,见 §C。R3 范围内:▲/◇ 定案 10 条 + 新发现 2 条,
无一条被推翻为"文档完全正确";其中 1 条 ◇(Tool Search)被证伪为"其实文档很全"。

## B. 需本人复核的两条

### B.1 hardline 底线的符号名 — 证伪;机制 — 证实(§8.1 复核)

`UNRECOVERABLE_BLOCKLIST` 这个符号 **全仓代码 0 命中**,只出现在 `website/docs/user-guide/security.md`
(及其中文镜像)。真实符号是 `HARDLINE_PATTERNS`(`tools/approval.py:434`)+ `detect_hardline_command`
(`tools/approval.py:520`)。亲测(在基线仓库根重跑,`verify` 围栏 = 自检命令,非源码摘录):

**R11C 片 C 改:原块是一段 `$` 提示符**转录**(命令与输出混排在同一个 ```verify 围栏里),原样重跑等于把输出行也当命令执行。下面拆成「可重跑命令 + 逐字输出」两块;转录里的旁注移到块后正文。**读数与原块一致,结论未变。**

```verify
cd /home/user/hermes-agent
grep -rn UNRECOVERABLE_BLOCKLIST tools/ agent/ model_tools.py; echo "code-side exit=$?"
grep -rln UNRECOVERABLE_BLOCKLIST .
```

```text
code-side exit=1
./website/docs/user-guide/security.md
./website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/security.md
```

`code-side exit=1` 即第一条 grep **零命中**(GNU grep 无匹配退出 1):代码面搜不到这个名字;
全仓搜只命中**两份文档**(中英各一),它们互为翻译。

*(R8-fix 修正:原写法 `grep UNRECOVERABLE_BLOCKLIST tools/ agent/ model_tools.py` 缺 `-r`,
对目录参数不会递归,重跑给出的是 "是个目录" 而不是"零命中";第二条只搜 `website/docs/`,
看不到 zh-Hans 镜像那一份。结论两条都不变,改的是**命令能否重跑复现**——同 M-16d。)*
**但机制描述正确**:它确是"yolo 之下的地板、在审批层看到命令之前触发、无覆盖标志"——层级顺序
`approval.py:3761`(hardline)早于 `:3789`(yolo),测试 `test_hardline_blocklist.py` 逐条钉死不可绕过性
(见 r3-95)。故:**符号名证伪(应改 `HARDLINE_PATTERNS`),机制证实**。这条同时回答 R1 的"分层命令审批
体系"◇——审批体系有文档(security.md),但符号名错、且"hardline/user-deny/sudo-guess 严格前置于所有
bypass"的边界顺序文档未讲透。

### B.2 check_fn "cached per-call" — 证实为 30s TTL + 60s 宽限

`website/docs/developer-guide/tools-runtime.md:91 @ 863e313` 称 check_fn 结果 "cached per-call"。实际是跨调用的 **30 秒 TTL 缓存**
(`tools/registry.py:216` `_CHECK_FN_TTL_SECONDS = 30.0`)+ **60 秒瞬断宽限**
(`:220` `_CHECK_FN_FAILURE_GRACE_SECONDS = 60.0`,一次探测在上次成功 60s 内失败则返回 last-good True),
且按 multiplex profile 维度隔离(`:246 check_fn_cache_scope`)。这条 R2 报告已收录为 §2.16-19,本轮在
r3-01 §2 给出实现证据,升级为"精读证实"。

## C. R3 新发现的注释/docstring 漂移

1. **fuzzy_match "9-strategy" docstring 差一条**:`tools/fuzzy_match.py:9-18` 模块 docstring 自称
   "9-strategy chain" 却只编号列了 8 条(亲测编号项 = 8),漏掉 `unicode_normalized`;实际 `strategies`
   列表(`:149-159`)是 9 条,`unicode_normalized` 作为第 7 位插在 `block_anchor` 前。docstring 编号清单陈旧。
2. **model_tools 内联注释的双重陈旧**:`model_tools.py:579` 内联注释称 tool_search "when the deferrable
   surface exceeds the configured threshold (default 10% of context window)",但代码真实默认
   `threshold_pct=5.0`(`tools/tool_search.py:111`),且 tiered 方案下 threshold **已不再 gate 激活**
   (改 gate listing 预算,`should_activate` 只看"有无可 defer 工具")。正文文档 tool-search.md 是对的,
   陈旧的只是这条模型侧内联注释。

两条都是**代码内注释/docstring 与代码**的漂移(非 website/docs 冲突),仍是学习产出,记录在案。

## D. 对报告的处置

以上 10 条定案 + 2 条新发现进 round-3 报告的"文档-代码冲突定案"节。以代码为准原则下,后续轮次引用
这些机制以本定案为准。最值得记住的三条:(1) 安全文档的**符号名**普遍滞后(UNRECOVERABLE_BLOCKLIST
不存在),但**机制描述**大体正确;(2) MCP 客户端侧的**7 项安全防护**(描述注入扫描、OSV 预检、
exfil/persistence/IOC 过滤、stdio watchdog 孤儿清理、命名撞车 fail-closed、schema 缓存复检、跨源鉴权剥离)
是本簇最大的"代码有、地图无"落差;(3) Tool Search 反倒是**文档比代码注释更全**的正面案例。
