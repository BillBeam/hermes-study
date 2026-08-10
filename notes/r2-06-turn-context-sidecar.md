# R2-06 TurnContext 回合前奏 + api_content『persist-what-you-send』侧车

> 底稿。基线 `863e31318`。范围:`agent/turn_context.py`(1275)、
> `agent/conversation_loop.py:475-611`(系统提示恢复)、`hermes_constants.py`(profile 边界,概述)。

## 0. 问题

6000 行循环里,一次性设置(系统提示恢复、preflight 压缩、插件/记忆注入、MCP 刷新)与循环体
纠缠会不可维护;更深的问题是**prompt cache 字节稳定**:注入内容若直接改写用户消息则污染持久转录;
若每次现注入则历史消息线上字节漂移,provider 缓存前缀从注入点整段失效。

## 1. build_turn_context:前奏收敛为一个函数(turn_context.py:337-457+)

返回 `TurnContext` dataclass(308-336)供循环解包。协作函数(restore_or_build_system_prompt、
install_safe_stdio、sanitize_surrogates 等)**以参数显式传入**,让本模块不 import conversation_loop、
避免 import 环(360-362 docstring)。前奏顺序(每步有理由):
1. `install_safe_stdio()`(365):防 systemd/headless 下 broken pipe 的 OSError。
2. `recover_rotated_compression_session`(370-372):采纳被其它路径轮转的会话历史。
3. `set_session_context(session_id)`(383):本线程日志打 session 标签供 `hermes logs`。
4. `set_current_write_origin`(386):绑定技能写来源 ContextVar。
5. `_restore_primary_runtime()`(389):上回合激活了 fallback 则恢复主运行时(见 r2-23 §3)。
6. `set_runtime_main(...)`(394-404):把活跃 provider/model 发布给 auxiliary_client(见 r2-21 §1.2)。
7. **between-turns MCP 刷新**(408-434):上回合后才连上的 MCP server(慢 HTTP/OAuth 常 2-6s)落入
   本回合工具快照。**缓存安全 by construction**:在前奏跑、在本回合首次 API 组装 `tools=` 之前,
   只扩展新请求前缀、绝不改在飞回合的缓存前缀;`sys.modules` 门(428-429):没导入过 `tools.mcp_tool`
   就没 MCP 工具可刷,直接跳过省 ~0.4s 导入。
8. surrogate 消毒(437-440)、stream_callback / persist override 存储(443-446)、task_id/turn_id 生成(448-456)。

之后依次:系统提示 restore-or-build → `_ensure_db_session`(在系统提示后建 DB 行,防 system_prompt=NULL
的首回合缓存 miss,#45499)→ preflight 压缩 → pre_llm_call 插件钩子 → 外部记忆预取 → api_content 组装。

## 2. 系统提示 restore-or-build 与静态前缀重建(agent/conversation_loop.py:475-611)

`_restore_or_build_system_prompt` 的三态区分(482-493,全部落日志让静默缓存 miss 可见):
`missing`(无会话行,合法首回合)/ `null`(行存在但列 NULL,遗留会话)/ `empty`(列为空串,
静默持久化 bug,总是 warn)/ `present`(可用,逐字复用)/ `stale_runtime`(存的提示身份过期,重建)。

关键:`stored_prompt` 命中且 `_stored_prompt_matches_runtime` → 复用存储的完整提示保 Anthropic 缓存
前缀匹配(524-527),并 `reconstruct_static_prefix`(539-541)重建跨会话稳定的前缀块——静态前缀**不持久化**
(只存完整提示),gateway 每回合新建 AIAgent 会丢两块布局、mid-conversation 翻转线形降级为单断点。
`reconstruct_static_prefix` gate 在 `_use_prompt_caching`、施加 startswith 安全门(存储字节永不改写)、
失败 fail-open 到 legacy 布局。DB 读写失败落 WARNING 而非 DEBUG(495-500:曾是 debug 级静默打断
gateway 路径的前缀缓存复用)。

## 3. api_content 侧车:四个原语(turn_context.py:53-171)

侧车不变式一句话:**"turn N 发出的字节 = turn N+1 回放的字节"**(64-69 docstring)。四原语:

- **compose_user_api_content**(53-85):当前回合 user 消息的 API 字节 = 干净 content + 记忆预取
  fenced block + 插件 pre_llm_call 上下文;仅 str content 有效(多模态返 None 原样发)。**唯一组装点**:
  前奏把结果盖章为 `api_content`(与干净 content 并存持久化),循环的 api_messages 构建发同一 helper
  输出,侧车永不与线上漂移。
- **substitute_api_content**(88-108):在每个 API 构建点 pop 侧车替换进 content(仅 user/assistant),
  保 provider 前缀跨回合字节稳定。
- **drop_stale_api_content**(111-120):内容被重写的路径(历史图片剥离、merge-summary-into-tail、
  连续 user 修复合并、过期确认脱敏)必须丢侧车——回放 pre-rewrite 侧车会重发刚删掉的东西;
  **代价是一个缓存边界 miss,永不是错误内容**。
- **extract_api_content_sidecar**(123-130):gateway/分支转发复制侧车到新行时用。

另两个 gateway 专用原语:`consume_gateway_turn_context_notes`(133-150,把易变的 per-turn 事实
——auto-reset/首次接触/语音变更——从系统提示搬到当前用户消息的侧车上一次性投递,保系统提示字节稳定)、
`append_notes_to_multimodal_content`(153-170,多模态 user 消息 compose 返 None 时,把 notes 作为
text part 直接 append 进 content 列表——成为持久内容按原样回放,线上与转录字节一致)。

## 4. reanchor:压缩后重新定位当前回合 user 消息(turn_context.py:173-198)

压缩用新拷贝替换列表项,并可能在幸存副本**之后**追加 todo-snapshot user 消息或恢复的 user 回合,
故压缩前的索引失效。策略:优先取**内容精确匹配本回合文本的最后一条 user 消息**(常见情形下的幸存
副本),让注入盖章与 #48677 持久 override 不落到 todo-snapshot 或历史行;无精确匹配则回退最后一条
user 消息(merge-summary-into-tail 改了内容但追踪器仍需活锚点);列表无 user 消息返 -1。

## 5. 重实现要点

1. 前奏收敛为纯函数,协作依赖用参数注入避免 import 环。
2. 注入走侧车:干净 content 与线上字节永久分离,持久化两者;组装只有一个入口,构建与持久共用它。
3. 内容重写路径必须主动丢侧车(边界 miss 换正确性)。
4. 静态前缀不持久化,复用时用"字面 startswith"重建;失败 fail-open 到 legacy 布局。
5. 缓存扩展类操作(MCP 刷新)只在"新回合首次请求前"做,永不碰在飞前缀。
6. 压缩会重排列表,任何跨回合追踪的锚点都要按内容重定位而非索引。
