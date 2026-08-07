# R6-90 文档-代码冲突定案(R6 范围)

> 底稿。基线 `863e31318`。判定用语:**证实 / 证伪 / 修正 / 补白**。每条附双方证据;
> 主线已对各子代理关键行号逐字复核。本轮的普遍规律:**8 家后端 README 全部落后于代码,
> 无一处代码落后于 README**——配置项缺失、工具漏列、死配置、惰性元数据是四大漂移形态。

## 定案 1 ◇ R1 条目「记忆检索查询改写(query_rewrite)」——证实(主线亲读)

R1 ◇9(query_rewrite.py:41)。查实:aux 任务 `memory_query_rewrite`;输入 JSON 化注明
"data only" + 系统提示明令不执行消息内指令;**输出过五道确定性闸**(≤320 字符、疑问词开头、
含记忆接地词、不含指令词汇 `_INSTRUCTION_LEAK_RE`、无内部多句),任一不过返回 `""` 退回原话
检索(query_rewrite.py:84-106, 109-139)。防注入是"输入嘱咐 + 输出形状闸"双层,比 R1 标记
描述更硬。

## 定案 2 ◇ 根 README:26「Honcho dialectic user modeling」——证实(主体在服务端)

Hermes 侧有完整 dialectic 调用编排(多 pass `peer.chat`、冷/暖提示词、比例 reasoning level、
`honcho_reasoning` 工具),但画像构建/自愈在 Honcho 后端;Hermes 是采集+调用+注入的客户端。
宣称当读作"集成了"而非"实现了"。

## 定案 3 ▲ honcho README 会话名优先级表——证伪

`README.md:230-242` 表:manual map(1)→ /title(2)→ gateway key(3)→ per-session(4)…
代码(client.py:793-806 docstring 与实现一致):**gateway key 绝对第一**,其次 per-session
(权威,防生成标题重映射活会话),再 manual map,再 title。行为差异实在:配了手工映射的网关
会话,代码用网关键。以代码为准。同类:`README.md:334-339` "Peer card fetch tokens 200" 的
预算**全插件不存在**(疑为已删旧实现化石);`writeFrequency` 四态在 manager `save()` 里实现
但 **provider 主路径绕过**(sync_turn 直接 flush;gateway 只剩孤儿注释 gateway/run.py:6107-6109)
——宣称的机制存在但未接线。另有代码内不一致:cli.py:1113 仍拼旧点号 host 键
(`f"{HOST}.{p.name}"`),写路径规范是下划线,status --all/peers 对新格式 profile 显示为空。

## 定案 4 ▲ openviking:两处 README 证伪 + 一处保守

- `README.md:86` "viking_search fast/deep/auto modes":代码只有二态
  (`endpoint = ".../search" if mode == "deep" else ".../find"`,__init__.py:4888),auto ≡ fast。
- `README.md:34-36` "copy 现有 profile 连接值进 Hermes":该路径在基线不存在(现有 profile 只有
  link;copy 只在新建流程)。
- `README.md:10-11` 要求先跑 server:实际本地端点不可达时运行期**自动拉起**(保守而非错)。
- 配置表缺 8 个 `OPENVIKING_RECALL_*` 等召回参数。

## 定案 5 ▲ hindsight:README 三处不全 + 惰性元数据

配置文件只写一级(实为 profile → legacy → env 三级);环境变量表缺 7 个真实生效变量;配置表缺
timeout/idle_timeout/prefetch_waits_for_retain 等 7 键。**plugin.yaml 声明 `hooks: [on_session_end]`
但类未实现该方法**——且全仓无代码消费 plugin.yaml 的 hooks 键(加载器只读 description),惰性
元数据与实现双重脱节。298s 事故的现防御证实为结构性(prefetch 零网络 + 单写者队列 + root 前置
检查 + 120s 单调用封顶 + drop 语义读后写栅栏)。

## 定案 6 ▲ supermemory:死配置

`README.md:55` `capture_mode` "Skip tiny or trivial turns by default":`_capture_mode` 被加载
(__init__.py:672)但**全文件无使用点**,`_is_trivial_message` 同为死代码——sync_turn 缓冲一切
非空轮,过滤已在演化中移除(测试注释留有痕迹)。README 描述的行为不存在。另 `api_timeout`
对 ingest 实为 +3s;kebab/snake 别名方向说反(行为等价)。

## 定案 7 ▲ retaindb:三处 README 证伪

- `README.md:3` "7 memory types":schema enum 只有 6 个(factual/preference/goal/instruction/
  event/opinion,__init__.py:113-117)。
- `README.md:33-40` 工具表 5 个:实注册 **10 个**(漏整个文件工具族 upload/list/read/ingest/delete)。
- `README.md:24` "All config via env":还读 config.yaml 的 `memory.retaindb` 块(#68209)。
  唯一 crash-safe 写路径(SQLite write-behind)README 只字未提,docstring 才是真地图。

## 定案 8 ▲ mem0:README 误导 + 代码内漂移

- `README.md:30` `user_id` 默认 `hermes-user`:该值实为**哨兵**,等于"未配置"、回落网关原生 id
  (__init__.py:56-62)——按 README 填会得到与预期不同的行为。
- `README.md:101` `--mode` 取值表漏 `selfhosted`(README 自己 49 行用了,内部矛盾)。
- 代码内:`_setup.py:954` 最低版本检查 (2,0,7) 落后 plugin.yaml 的 `mem0ai>=2.0.10`。
- 三形态路由(oss > host > platform)与熔断(5 败/120s,客户端错误豁免)证实且测试钉死。

## 定案 9 ▲ holographic:配置文档两处各缺一半 + 命名暗坑

实际可配 7 键;README 列 4 键、模块 docstring 列另一半,任一处都不全。插件名 `holographic`
但配置键是历史名 `plugins.hermes-memory-store`,README 未解释。`store.py` 的 `search_facts`/
`rebuild_all_vectors` 为死代码(全仓无调用,grep 实证)。HRR 相位数学、进程级共享连接注册表、
FTS5 查询消毒均证实且有行为规格。

## 定案 10 memory-providers.md 总览页——证实

"8 external providers / one active at a time / built-in always active alongside"(:9)与代码一致
(8 个 bundled 目录、MemoryManager 单外部注册纪律、内建独立于 manager)。各家小节的细节漂移
归入上述各定案。

## 定案 11 optimize-storage 深水区(主线亲读)——r5-10 结论复核成立 + 三条补充

打章 = 三条件 × 两次检查(事务外 + 写事务内),章是"完全完成"唯一事实源;降级手术的标记先于
空 schema 落地(`executescript` 隐式 COMMIT 不能进写事务是硬约束);`fts_optimize_available`
五路判定含对旧版本崩溃窗产物的向后治愈。占空比节流(sleep ≥ 4×块耗时)单点在编排层。

## 定案 12 MCP OAuth 三件套(R3-structure 清账)——主线复核成立,新增两条文档证伪

机制定性(r6-60):协议全托 MCP SDK(OAuth 2.1 授权码 + PKCE S256 + RFC 7591 DCR + RFC 9728/
8414 双段发现 + RFC 8707 resource),Hermes 只做三块胶水(0600 原子 token 存储 + 绝对过期播种、
loopback 回调"预留即持有"端口 + 粘贴回退、manager 单例 + 盘监视 + 401 去重 + invalid_client
自愈);dashboard 模式把两个人机回调改道为免鉴权路由上以 state 为能力凭证的会合点。手写 `asend`
双向生成器桥是一次真实事故的修复(`async for` 转发丢弃 asend 值,每个 OAuth server 首响应即炸)。

两条文档证伪(主线逐字复核):
- **▲ `oauth-over-ssh.md:152`**:"the latest `Waiting for callback on ...` line (Hermes may
  auto-bump if the preferred port is busy)"——该提示串全仓零命中,且端口被占**不 auto-bump**、
  直接抛可行动错误(mcp_oauth.py:889-893);auto-bump 恰是"缓存端口一致性"设计要避免的。
- **▲ `mcp-config-reference.md:314`**:"Only applies to HTTP/StreamableHTTP transport"——代码
  显式支持 SSE OAuth(mcp_tool.py:2822-2826,注释自记"Previously built but never forwarded —
  SSE OAuth would silently fail"),文档滞后于该修复。

## 小结

| # | 条目 | 判定 |
|---|---|---|
| 1 | query_rewrite ◇(R1) | 证实(双层防注入) |
| 2 | 根 README Honcho 宣称 | 证实(主体在服务端) |
| 3 | honcho 会话名优先级表 / card 200 / writeFrequency | **证伪 ×3** |
| 4 | openviking auto 模式 / copy-profile 路径 | **证伪 ×2** |
| 5 | hindsight 配置文档 ×3 / plugin.yaml hooks | 修正 + 惰性元数据 |
| 6 | supermemory capture_mode | **证伪**(死配置) |
| 7 | retaindb 7 类型 / 5 工具 / 纯 env | **证伪 ×3** |
| 8 | mem0 user_id 默认值 / --mode 表 / 版本检查 | 证伪 + 内部矛盾 + 代码漂移 |
| 9 | holographic 配置文档 / 死代码 / 命名 | 修正 + 补白 |
| 10 | memory-providers.md 总览 | 证实 |
| 11 | optimize-storage 编排 | 证实(r5-10 复核) |
| 12 | MCP OAuth 清账 | 见 r6-60 |

**本轮元规律**:插件 README 的漂移方向 100% 是"文档落后代码";最易腐烂的是**表格类宣称**
(优先级表、数值限制表、配置项表、工具清单)——重实现时凡表格要么从代码生成、要么用测试钉死。
plugin.yaml 的 `hooks` 键全仓无消费者,声明性元数据与分发机制脱节是系统性风险(hindsight、
byterover、openviking 三家的 hooks 声明各自与实现不符)。
