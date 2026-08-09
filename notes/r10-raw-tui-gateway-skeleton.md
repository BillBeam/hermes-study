# r10-A · tui_gateway 协议骨架与传输 —— 一个 14,006 行入口模块的接口面测绘

> 底稿(证据层),求全求证不求好读。基线 `/home/user/hermes-agent` @ `863e31318553cda8ad61df681d08175364d4164b`,
> 引用后缀 `@ 863e313`。锚点一律单独成行、置于紧跟其后的代码块之前;
> 表格里的锚点一律写成「锚点 + 紧跟的反引号摘录」的声明式形式,以便被机械校验。
> 全文引用一律用**从仓库根可解析的全路径**(不写 `ws.py:38` 这种裸文件名)。
> 片内 11 个文件 / 15,821 行,清单见 `data/r10/slices/A.txt`。

---

## §1 这一片是什么

**JSON-RPC**(JSON Remote Procedure Call)= 用 JSON 报文表达「调哪个方法、参数是什么、返回什么」
的轻量远程调用约定。请求形如 `{"jsonrpc":"2.0","id":7,"method":"prompt.submit","params":{…}}`,
响应形如 `{"jsonrpc":"2.0","id":7,"result":{…}}` 或 `…"error":{"code":…,"message":…}`。
另有一种**无 id 的通知**方向:服务端主动推送 `{"jsonrpc":"2.0","method":"event","params":{"type":"…"}}`,
客户端不回。hermes-agent 里前者叫「方法」,后者叫「事件」。

`tui_gateway` 是**终端 UI / 桌面 App(TypeScript)与 Python agent 内核之间的这座桥的 Python 侧**。
它不是 HTTP 服务:默认形态是 Node 父进程 `spawn` 一个 Python 子进程,双方用**换行分隔的 JSON 行**
在 stdin/stdout 上对讲。另有一条 WebSocket 通道给桌面 App 与 dashboard 的「Chat」标签页复用同一套 handler。

本片是这座桥的**骨架**,不含业务 handler 的实现体(那些在 `tui_gateway/methods_*.py`,属别的片):

- **进程入口**:`tui_gateway/entry.py` —— stdio 形态的 `main()` 读循环、信号处理、崩溃取证。
- **传输层**:`tui_gateway/transport.py` —— 「一个能吞 dict 的 sink」这个抽象 + contextvar 绑定 +
  stdio 实现 + 一分二的 Tee。
- **WebSocket 通道**:`tui_gateway/ws.py` —— 每连接一个 transport、token 合批、断连拆除。
- **事件旁路扇出**:`tui_gateway/event_publisher.py` —— 把 PTY 子进程里 gateway 的事件反向推给
  dashboard 侧边栏。
- **两块事故化石**:`tui_gateway/_stdin_recovery.py`(子进程翻 `O_NONBLOCK` 导致的假 EOF)、
  `tui_gateway/loop_noise.py`(WS 对端硬断导致的 asyncio 回溯洪水)。
- **回合标记**:`tui_gateway/turn_marker.py` —— 进程猝死后判定「哪个 turn 没跑完」的落盘证据。
- **渲染桥**:`tui_gateway/render.py` —— 把 TUI 内容交给 Python 侧渲染器
  (**本基线上永久失效,见 §6 ■-1**)。
- **handler 拆分接缝**:`tui_gateway/method_ctx.py` —— 把 handler 搬出 server.py
  而**不改一行 handler 体**的机制。
- **主体**:`tui_gateway/server.py`(14,006 行)—— 方法注册表、`dispatch`、`write_json` 路由阶梯、
  会话注册表与其生命周期、以及大量供 `methods_*` 闭包引用的模块级状态。

---

## §2 文件清单(逐个全路径 + 一句话角色)

| 全路径 | 行数 | 角色 |
|---|---|---|
| `tui_gateway/__init__.py` | 0 | **空文件**,仅作包标记(`wc -c` = 0 字节)。包内一律用 `tui_gateway.X` 绝对导入,不靠 `__init__` 做 re-export。 |
| `tui_gateway/entry.py` | 499 | stdio 形态的进程入口:路径加固 → 信号安装 → sidecar 挂载 → MCP 发现后台启动 → 发 `gateway.ready` → 读循环。 |
| `tui_gateway/transport.py` | 219 | 传输抽象:`Transport` Protocol、contextvar 当前传输、`StdioTransport`(换行帧 + 锁 + 「对端没了 vs 主机 I/O 真出错」的 errno 分诊)、`TeeTransport`(一主 N 从)。 |
| `tui_gateway/ws.py` | 476 | WebSocket 通道:`WSTransport`(跨线程投递 + 逐 token 合批)+ `handle_ws`(一次连接的完整生命周期,含断连拆除)。 |
| `tui_gateway/event_publisher.py` | 126 | `WsPublisherTransport`:PTY 子进程里的 gateway 反向连 dashboard 的 `/api/pub`,把每一帧镜像过去喂侧边栏;有界队列、满即丢、失败即哑。 |
| `tui_gateway/server.py` | 14,006 | 全片主体:`_methods` 注册表、`dispatch`/`handle_request`、`write_json` 路由阶梯、`_emit`/`_event_frame`/`_broadcast_global_event`、会话注册表 `_sessions` 与 TTL/LRU/孤儿回收、agent 工厂、阻塞式提问工厂、变更监视器、voice/wake、以及 21 个自持 handler。 |
| `tui_gateway/method_ctx.py` | 53 | `HandlerRegistry`:延迟注册 + 用 `types.FunctionType` 把 handler 的 `__globals__` 重绑到 server.py 命名空间,使 handler 体**字节不变**地搬出 server.py。 |
| `tui_gateway/turn_marker.py` | 159 | 「回合标记」落盘 sidecar:turn 开跑前写、结束即清;残留即证明进程猝死。`session.resume` 据此自动续跑。 |
| `tui_gateway/_stdin_recovery.py` | 151 | 假 EOF 恢复:子进程给共享 open file description 翻了 `O_NONBLOCK`(或设了 `SO_RCVTIMEO`),导致 gateway 的 `readline()` 返回 `''` 被误判为对端关闭;此模块分诊并恢复,带每分钟 10 次的速率上限。 |
| `tui_gateway/loop_noise.py` | 83 | asyncio 事件循环异常处理器链:把「对端写到一半挂了」这一类 transport 拆除回溯折叠成一行 debug,其余原样转给默认处理器。 |
| `tui_gateway/render.py` | 49 | 渲染桥:若 `agent.rich_output` 存在则用它渲染 markdown / diff / 流式内容,否则全返回 `None` 让 TUI 用自己的 `markdown.tsx`。**本基线上 `agent/rich_output.py` 不存在,故三个函数恒返回 `None`(§6 ■-1)。** |

合计 15,821 行,与派工清单一致。

```verify
# 片内文件与行数复核(可重跑)
cd /home/user/hermes-agent && wc -l $(sed 's|^|/home/user/hermes-agent/|' /home/user/hermes-study/data/r10/slices/A.txt) | tail -1
```

---

## §3 接缝穷举

### 3.1 JSON-RPC 方法表 —— **144 条,全列**

注册靠两个装饰器:`tui_gateway/server.py` 的 `method(name)`,以及 projects 子面专用的
`_projects_method(name)`(后者在内部再调 `method(name)`)。`methods_*.py` 里的 `method` 是
`HandlerRegistry.method` 的别名(`from .method_ctx import HandlerRegistry` →
`_registry = HandlerRegistry()` → `method = _registry.method`),
所以**六个文件用的都是行首 `@method("…")` 这一种写法**,一条 grep 即可穷举。

```verify
# 机械枚举:144 条方法名(静态,不 import)
cd /home/user/hermes-agent && grep -ho '^@\(method\|_projects_method\)("[^"]*")' tui_gateway/*.py \
  | sed 's/.*("\(.*\)")/\1/' | sort -u | wc -l
# → 144

# 交叉验证:运行时注册表条数(需 venv;HERMES_HOME 指向临时目录避免写用户目录)
HERMES_HOME=$(mktemp -d) HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python -c \
  "from tui_gateway import server; print(len(server._methods))"
# → 144(与静态枚举一致,说明没有第三种注册路径)

# 每个文件各注册多少
cd /home/user/hermes-agent && for f in tui_gateway/server.py tui_gateway/methods_session.py \
    tui_gateway/methods_tools.py tui_gateway/methods_prompt.py tui_gateway/methods_config.py \
    tui_gateway/methods_complete.py; do \
  printf "%-34s %s\n" "$f" "$(grep -c '^@\(method\|_projects_method\)("' $f)"; done
# → server.py 21 / methods_session.py 62 / methods_tools.py 32
#    methods_prompt.py 16 / methods_config.py 7 / methods_complete.py 6   (合计 144)
```

**注册表的唯一权威定义**,`tui_gateway/server.py:1864 @ 863e313`

```
def method(name: str):
    def dec(fn):
        _methods[name] = fn
        return fn

    return dec
```

**按拥有者文件分组的 144 条全表**(本片只拥有第一组 21 条;其余四组的实现体属别的片,
但它们全部落在 `server._methods` 这一张表里,所以协议面必须一并列):

**A. `tui_gateway/server.py`(21 条)** —
`config.set`、`projects.add_folder`、`projects.archive`、`projects.create`、`projects.delete`、
`projects.for_cwd`、`projects.get`、`projects.list`、`projects.remove_folder`、`projects.set_active`、
`projects.set_primary`、`projects.update`、`voice.record`、`voice.toggle`、`voice.tts`、
`wake.feed`、`wake.pause`、`wake.resume`、`wake.start`、`wake.status`、`wake.stop`

**B. `tui_gateway/methods_session.py`(62 条)** —
`billing.auto_reload`、`billing.charge`、`billing.charge_status`、`billing.state`、`billing.step_up`、
`delegation.pause`、`delegation.status`、`handoff.fail`、`handoff.request`、`handoff.state`、
`llm.oneshot`、`message.react`、`pet.cancel`、`pet.cells`、`pet.disable`、`pet.export`、`pet.gallery`、
`pet.generate`、`pet.generate.status`、`pet.hatch`、`pet.info`、`pet.info.meta`、`pet.remove`、
`pet.rename`、`pet.scale`、`pet.select`、`pet.thumb`、`project.facts`、`session.activate`、
`session.active_list`、`session.branch`、`session.close`、`session.compress`、
`session.context_breakdown`、`session.create`、`session.cwd.set`、`session.delete`、`session.history`、
`session.interrupt`、`session.list`、`session.most_recent`、`session.redirect`、`session.resume`、
`session.save`、`session.status`、`session.steer`、`session.title`、`session.undo`、`session.usage`、
`session.workspace.move`、`spawn_tree.list`、`spawn_tree.load`、`spawn_tree.save`、`subagent.interrupt`、
`subscription.change`、`subscription.preview`、`subscription.resume`、`subscription.state`、
`subscription.upgrade`、`terminal.resize`、`usage.bars`、`verification.status`

**C. `tui_gateway/methods_tools.py`(32 条)** —
`agents.list`、`browser.manage`、`cli.exec`、`command.dispatch`、`command.resolve`、`commands.catalog`、
`config.show`、`cron.manage`、`insights.get`、`learning.delete`、`learning.detail`、`learning.edit`、
`learning.frames`、`plugins.list`、`plugins.manage`、`process.kill`、`process.list`、`process.stop`、
`reload.env`、`reload.mcp`、`rollback.diff`、`rollback.list`、`rollback.restore`、`shell.exec`、
`skills.manage`、`skills.reload`、`slash.exec`、`system.battery`、`tools.configure`、`tools.list`、
`tools.show`、`toolsets.list`

**D. `tui_gateway/methods_prompt.py`(16 条)** —
`approval.respond`、`clarify.respond`、`clipboard.paste`、`file.attach`、`image.attach`、
`image.attach_bytes`、`image.detach`、`input.detect_drop`、`pdf.attach`、`preview.read.respond`、
`preview.restart`、`prompt.background`、`prompt.submit`、`secret.respond`、`sudo.respond`、
`terminal.read.respond`

**E. `tui_gateway/methods_config.py`(7 条)** —
`config.get`、`projects.discover_repos`、`projects.project_sessions`、`projects.record_repos`、
`projects.tree`、`setup.runtime_check`、`setup.status`

**F. `tui_gateway/methods_complete.py`(6 条)** —
`complete.path`、`complete.slash`、`model.disconnect`、`model.options`、`model.save_key`、`paste.collapse`

**未知方法的错误码**是标准 JSON-RPC 的 `-32601`,`tui_gateway/server.py:1891 @ 863e313`

```
def handle_request(req: dict) -> dict | None:
    normalized = _normalize_request(req)
    if isinstance(normalized, dict):
        return normalized

    rid, method, params = normalized
    fn = _methods.get(method)
    if not fn:
        return _err(rid, -32601, f"unknown method: {method}")
    return fn(rid, params)
```

请求合法性校验(在查表之前),`tui_gateway/server.py:1872 @ 863e313`

```
def _normalize_request(req: Any) -> tuple[Any, str, dict] | dict:
    """Validate a JSON-RPC request enough for safe local dispatch."""
    if not isinstance(req, dict):
        return _err(None, -32600, "invalid request: expected an object")

    rid = req.get("id")
    method = req.get("method")
    if not isinstance(method, str) or not method:
        return _err(rid, -32600, "invalid request: method must be a non-empty string")

    params = req.get("params", {})
    if params is None:
        params = {}
    elif not isinstance(params, dict):
        return _err(rid, -32602, "invalid params: expected an object")

    return rid, method, params
```

**协议层错误码合计 6 个**(业务层用四位数自定义值,如 `5032`/`4009`/`5061`–`5063`,不占 JSON-RPC 保留段):

| 码 | 语义 | 产生处(锚点 + 摘录) |
|---|---|---|
| `-32700` | parse error(stdio) | `tui_gateway/entry.py:485` 的 `if not write_json({"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}, "id": None}):` |
| `-32700` | parse error(WS) | `tui_gateway/ws.py:373` 的 `"error": {"code": -32700, "message": "parse error"},` |
| `-32600` | invalid request | `tui_gateway/server.py:1875` 的 `return _err(None, -32600, "invalid request: expected an object")` |
| `-32602` | invalid params | `tui_gateway/server.py:1886` 的 `return _err(rid, -32602, "invalid params: expected an object")` |
| `-32601` | unknown method | `tui_gateway/server.py:1899` 的 `return _err(rid, -32601, f"unknown method: {method}")` |
| `-32603` | internal error(WS 的 dispatch 崩溃兜底) | `tui_gateway/ws.py:404` 的 `"error": {"code": -32603, "message": "internal error"},` |
| `-32000` | 池内 handler 抛异常 | `tui_gateway/server.py:1933` 的 `resp = _err(req.get("id"), -32000, f"handler error: {exc}")` |

### 3.2 对外事件类型表 —— **64 种,全列**

**先确立穷举的完备性**:服务端推给客户端的事件帧,在**整个 `tui_gateway/` 包里只有 4 处**被构造。

```verify
# 搜索面:tui_gateway/ 全部 22 个 .py 文件,搜 '"method": "event"' 字面量
cd /home/user/hermes-agent && grep -n '"method": "event"' tui_gateway/*.py
# → 只有 4 处:
#   tui_gateway/entry.py:445            (stdio 的 gateway.ready)
#   tui_gateway/host_supervisor.py:493  (compute host 的 error;不属本片文件,但属同一事件宇宙)
#   tui_gateway/server.py:1536          (_event_frame —— 其余全部事件的唯一出口)
#   tui_gateway/ws.py:317               (WS 的 gateway.ready)
```

所以事件宇宙 = 「`_event_frame` 的第一参数取值全集」+ 3 个直接构造的帧。
`_event_frame` 只被 `_emit` / `_broadcast_global_event` 调用,于是用 AST 枚举
四个发射器的第一参数即可,再逐个解决动态参数。

```verify
# 机械枚举:字面量事件类型(AST,不靠正则,避免把 '.' 当通配符)
cd /home/user/hermes-agent && python3 -c "
import ast, pathlib, collections
lit=collections.Counter(); dyn=[]
E={'_emit','_voice_emit','_broadcast_global_event','_event_frame'}
for p in sorted(pathlib.Path('tui_gateway').glob('*.py')):
    for n in ast.walk(ast.parse(p.read_text())):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in E:
            a=n.args[0] if n.args else None
            if isinstance(a,ast.Constant) and isinstance(a.value,str): lit[a.value]+=1
            else: dyn.append((str(p),n.lineno,n.func.id,ast.unparse(a) if a else '-'))
print('literal:',len(lit)); print('dynamic sites:',len(dyn))
for d in dyn: print(' ',d)
"
# → literal: 39   dynamic sites: 9
```

九处动态第一参数,逐个定死:

| 动态点(锚点 + 摘录) | 解析结果 | 贡献的事件类型 |
|---|---|---|
| `tui_gateway/server.py:1540` 的 `write_json(_event_frame(event, sid, payload))` | `_emit` 自身的转发,非新增 | — |
| `tui_gateway/server.py:1576` 的 `_emit(event, "", payload)` | `_broadcast_global_event` 无客户端时的回落 | — |
| `tui_gateway/server.py:1579` 的 `frame = _event_frame(event, "", payload)` | 同上,广播路径 | — |
| `tui_gateway/server.py:3117` 的 `_emit(event, sid, payload)` | `_block(event, …)` 的五个调用点(`server.py:5655/5672/5682/5773/5780`) | `clarify.request`、`terminal.read.request`、`preview.read.request`、`sudo.request`、`secret.request` |
| `tui_gateway/server.py:3143` 的 `f"{event.removesuffix('.request')}.expire",` | 白名单五项的超时补发 | `clarify.expire`、`terminal.read.expire`、`preview.read.expire`、`sudo.expire`、`secret.expire` |
| `tui_gateway/server.py:3425` 的 `_broadcast_global_event(event, payload_fn())` | 遍历 `_CHANGE_WATCHES` 的键 | `pet.changed`、`cron.changed`、`sessions.changed`、`platforms.changed`、`pairing.changed` |
| `tui_gateway/server.py:5520` 的 `_emit(event_type, sid, payload)` | `_on_tool_progress` 的 `subagent.*` 中继(`subagent.text` **不发给父会话**) | `subagent.spawn_requested`、`subagent.start`、`subagent.thinking`、`subagent.tool`、`subagent.progress`、`subagent.complete` |
| `tui_gateway/server.py:9334` 的 `desktop_ui.set_emitter(lambda sid, event, payload: _emit(event, sid, payload))` | 调用方是 `tools/focus_pane_tool.py:26`、`tools/open_preview_tool.py:46`、`tools/react_to_message_tool.py:80` | `pane.reveal`、`preview.open`、`message.reaction` |
| `tui_gateway/server.py:12649` 的 `_emit(event, sid, payload)` | `_voice_emit` 自身的转发,其字面量调用点已计入 39 | — |
| 直接构造 | `tui_gateway/entry.py:448` 的 `"type": "gateway.ready",` + `tui_gateway/ws.py:319` 的 `"type": "gateway.ready",` | `gateway.ready` |

39 + 5 + 5 + 5 + 6 + 3 + 1 = **64 种**。

**五个 `.request` 事件的超时补发**(阻塞式提问的生命周期尾巴),`tui_gateway/server.py:3134 @ 863e313`

```
    # afterward. Without this the late `*.respond` would hit the generic 4009
    # "no pending request" error and clients would surface a raw JSON-RPC string.
    if not answered and not answer_present and event in {
        "secret.request",
        "sudo.request",
        "clarify.request",
        "terminal.read.request",
        "preview.read.request",
    }:
        _emit(
            f"{event.removesuffix('.request')}.expire",
            sid,
            {"request_id": rid},
        )
```

**五个 `*.changed` 事件的来源表**(轮询式变更侦测,不是推送),`tui_gateway/server.py:3380 @ 863e313`

```
_CHANGE_WATCHES: dict[str, tuple[float, Any, Any]] = {
    "pet.changed": (2.0, _pet_sig, _pet_changed_payload),
    "cron.changed": (1.0, _cron_sig, lambda: {}),
    "sessions.changed": (0.5, _sessions_sig, lambda: {}),
    "platforms.changed": (2.0, _platforms_sig, lambda: {}),
    "pairing.changed": (2.0, _pairing_sig, lambda: {}),
}
```

**64 种全表(按语义分组)**:

| 组 | 事件类型 |
|---|---|
| 握手 | `gateway.ready` |
| 会话状态 | `session.info`、`session.title`、`session.reclaimed` |
| 助手回复流 | `message.start`、`message.delta`、`message.interim`、`message.complete` |
| 推理流 | `thinking.delta`、`reasoning.delta`、`reasoning.available` |
| 工具 | `tool.start`、`tool.generating`、`tool.complete`、`tool.output_risk` |
| 子代理(委派) | `subagent.spawn_requested`、`subagent.start`、`subagent.thinking`、`subagent.tool`、`subagent.progress`、`subagent.complete` |
| MoA(多模型聚合) | `moa.reference`、`moa.aggregating`、`moa.progress`、`moa.phase` |
| 阻塞式提问(请求) | `approval.request`、`clarify.request`、`sudo.request`、`secret.request`、`terminal.read.request`、`preview.read.request` |
| 阻塞式提问(超时) | `clarify.expire`、`sudo.expire`、`secret.expire`、`terminal.read.expire`、`preview.read.expire` |
| 状态条 / 通知 | `status.update`、`notification.show`、`notification.clear` |
| 变更广播(无 sid) | `skin.changed`、`pet.changed`、`cron.changed`、`sessions.changed`、`platforms.changed`、`pairing.changed` |
| 语音 / 唤醒词 | `voice.status`、`voice.transcript`、`voice.interrupted`、`wake.detected` |
| 终端 / 预览 | `agent.terminal.output`、`terminal.close`、`preview.restart.progress`、`preview.restart.complete`、`preview.open`、`pane.reveal` |
| 宠物(petdex) | `pet.generate.progress`、`pet.hatch.progress` |
| 其他 | `error`、`reaction`、`message.reaction`、`review.summary`、`background.complete`、`browser.progress`、`billing.step_up.verification` |

**事件类型的产生地也是分裂的**(与 §6 ▲-8 相关):字面量 39 种里,
`tui_gateway/server.py` 34 种、`tui_gateway/methods_prompt.py` 6 种、
`tui_gateway/methods_session.py` 4 种、`tui_gateway/methods_tools.py` 1 种
(有重叠,`session.info` 四处都发)。

**与 TypeScript 客户端声明的类型联集对账**(交叉验证,同时是发现来源):

```verify
# TS 侧 GatewayEvent 联集成员数
cd /home/user/hermes-agent && sed -n '603,741p' ui-tui/src/gatewayTypes.ts \
  | grep -oE "type: '[^']+'( \| '[^']+')*" | grep -oE "'[^']+'" | tr -d "'" | sort -u | wc -l
# → 46
```

**只在 TS 侧、Python 从不发的 5 种**,以及它们真正的产生处:

| 事件类型 | Python 侧命中 | TS 侧产生处(锚点 + 摘录) |
|---|---|---|
| `gateway.stderr` | 0 | `ui-tui/src/gatewayClient.ts:380` 的 `this.publish({ type: 'gateway.stderr', payload: { line } })` |
| `gateway.start_timeout` | 0 | `ui-tui/src/gatewayClient.ts:249` 的 `type: 'gateway.start_timeout',` |
| `gateway.protocol_error` | 0 | `ui-tui/src/gatewayClient.ts:341` 的 `this.publish({ type: 'gateway.protocol_error', payload: { preview } })` |
| `dashboard.new_session_requested` | 0 | `ui-tui/src/app/useInputHandlers.ts:615` 的 `type: 'dashboard.new_session_requested'` |
| `tool.progress` | 1(**另一个 surface**) | `gateway/platforms/api_server.py:3735` 的 `_enqueue("tool.progress", {"message_id": message_id, "tool_name": tool_name or "_thinking", "delta": preview or ""})` |

**负结论的搜索面**:对这 5 个名字做**点号转义**的带引号字面量搜索,覆盖全仓所有 `*.py`(含 `tests/`),
唯一命中就是上表最后一行——那是 OpenAI 兼容 HTTP API 的 SSE 流,不经 `tui_gateway`。
前四个在 Python 侧零命中。

```verify
# 可重跑的那一条(点号必须转义,否则 tool.progress 会匹配到配置键 tool_progress,
# 在 100+ 个文件里命中,给出与结论相反的印象)
cd /home/user/hermes-agent && grep -rEn --include=*.py \
  "['\"](dashboard\.new_session_requested|gateway\.protocol_error|gateway\.start_timeout|gateway\.stderr|tool\.progress)['\"]" .
# → 1 行:./gateway/platforms/api_server.py:3735
```

**只在 Python 侧、Ink TUI 的类型联集未声明的 23 种**(桌面 / dashboard 独有,或 Ink 侧默默忽略):
`agent.terminal.output`、`clarify.expire`、`cron.changed`、`message.reaction`、`pairing.changed`、
`pane.reveal`、`pet.changed`、`pet.generate.progress`、`pet.hatch.progress`、`platforms.changed`、
`preview.open`、`preview.read.expire`、`preview.read.request`、`preview.restart.complete`、
`preview.restart.progress`、`session.reclaimed`、`session.title`、`sessions.changed`、
`terminal.close`、`terminal.read.expire`、`terminal.read.request`、`tool.output_risk`、
`voice.interrupted`。

### 3.3 传输帧格式 —— 三条通道,**三种帧规矩**

| 通道 | 出站帧 | 入站帧 | 边界由谁定 |
|---|---|---|---|
| stdio(`tui_gateway/transport.py:100` 的 `class StdioTransport:`) | `json.dumps(obj, ensure_ascii=False) + "\n"`,写入 `_real_stdout`,`flush` 可关 | `sys.stdin.readline()` 一行一帧,`strip()` 后 `json.loads` | **换行符** |
| WebSocket(`tui_gateway/ws.py:70` 的 `class WSTransport:`) | `json.dumps(obj, ensure_ascii=False)`,**不加换行**,一帧一个 WS text message;合批时一批 N 帧发成 **N 条 message** | `await ws.receive_text()` 一条 message 一帧,`strip()` 后 `json.loads` | **WebSocket message 边界** |
| 旁路 WS(`tui_gateway/event_publisher.py:40` 的 `class WsPublisherTransport:`) | `json.dumps(obj, ensure_ascii=False)`,**不加换行**,经内存队列由守护线程 `ws.send` | 单向,不收 | **WebSocket message 边界** |

stdio 侧的换行,`tui_gateway/transport.py:137 @ 863e313`

```
        line = json.dumps(obj, ensure_ascii=False) + "\n"

        with self._lock:
            stream = self._stream_getter()
```

WS 侧同一位置**没有**换行,`tui_gateway/ws.py:118 @ 863e313`

```
    def write(self, obj: dict) -> bool:
        if self._closed:
            return False

        line = json.dumps(obj, ensure_ascii=False)
```

WS 的 `write_async`(loop 线程用的那条路)也一样,`tui_gateway/ws.py:220 @ 863e313`

```
        # and the frame that drained them.
        with self._token_lock:
            batch = self._pending_tokens
            self._pending_tokens = []
            batch.append(json.dumps(obj, ensure_ascii=False))
        await self._safe_send_many(batch)
        return not self._closed
```

旁路 WS 也一样,`tui_gateway/event_publisher.py:90 @ 863e313`

```
    def write(self, obj: dict) -> bool:
        if self._dead or self._ws is None or self._worker is None:
            return False

        line = json.dumps(obj, ensure_ascii=False)

        try:
            self._q.put_nowait(line)

            return True
        except queue.Full:
            return False
```

WS 入站是「一条 message 一个 JSON」,不做换行切分,`tui_gateway/ws.py:354 @ 863e313`

```
            line = raw.strip()
            if not line:
                continue
            messages += 1

            try:
                req = json.loads(line)
```

**客户端侧的两套读写规矩印证了这个不对称**(这条不对称直接推翻 `ws.py` 自己的 docstring,见 §6 ▲-3):

| 方向 | stdio(锚点 + 摘录) | WebSocket(锚点 + 摘录) |
|---|---|---|
| 读 | `ui-tui/src/gatewayClient.ts:359` 的 `this.stdoutRl = createInterface({ input: this.proc.stdout! })` —— 行读器 | `apps/shared/src/json-rpc-gateway.ts:359` 的 `frame = JSON.parse(text) as JsonRpcFrame` —— 整条 message |
| 写 | `ui-tui/src/gatewayClient.ts:764` 的 `this.proc!.stdin!.write(JSON.stringify({ id, jsonrpc: '2.0', method, params }) + '\n')` —— **补换行** | `ui-tui/src/gatewayClient.ts:709` 的 `ws.send(JSON.stringify({ id, jsonrpc: '2.0', method, params }))` —— **不补** |

### 3.4 并发路由表:`_LONG_HANDLERS` —— **42 条走线程池,其余 102 条内联**

```verify
# 机械枚举:池路由集合的条数,并核对每一项都是真实注册过的方法名
cd /home/user/hermes-agent && python3 -c "
import ast
t=ast.parse(open('tui_gateway/server.py').read())
for n in ast.walk(t):
    if isinstance(n,ast.Assign) and any(getattr(x,'id','')=='_LONG_HANDLERS' for x in n.targets):
        names=sorted(e.value for e in n.value.args[0].elts); print(len(names)); print(' '.join(names))
"
# → 42;与 §3.1 的 144 条方法名做 comm -23 后为空(无失效条目)
```

42 条全列:`billing.state`、`billing.step_up`、`browser.manage`、`cli.exec`、`complete.path`、
`complete.slash`、`learning.frames`、`llm.oneshot`、`model.options`、`pet.cells`、`pet.gallery`、
`pet.generate`、`pet.hatch`、`pet.info`、`pet.select`、`pet.thumb`、`plugins.manage`、`process.list`、
`projects.discover_repos`、`projects.for_cwd`、`projects.project_sessions`、`projects.record_repos`、
`projects.tree`、`reload.mcp`、`session.active_list`、`session.branch`、`session.compress`、
`session.list`、`session.resume`、`session.usage`、`session.workspace.move`、`setup.runtime_check`、
`setup.status`、`shell.exec`、`skills.manage`、`slash.exec`、`subscription.change`、
`subscription.preview`、`subscription.resume`、`subscription.state`、`subscription.upgrade`、
`usage.bars`

**注意 `prompt.submit` 不在其中**:它内联执行,但**立刻返回** `{"status": "streaming"}`
并把真正的 turn 交给一条新守护线程(见 §4)。这是有意的——提交必须比任何池排队都快。

### 3.5 本片的环境变量开关

```verify
cd /home/user/hermes-agent && grep -nHo 'environ\.get("[A-Z_]*"\|getenv("[A-Z_]*"' \
  tui_gateway/entry.py tui_gateway/transport.py tui_gateway/ws.py \
  tui_gateway/event_publisher.py tui_gateway/turn_marker.py \
  tui_gateway/loop_noise.py tui_gateway/_stdin_recovery.py \
  tui_gateway/render.py tui_gateway/method_ctx.py
# → 只有 3 条(其余 6 个文件零环境变量)
```

| 变量 | 定义处(锚点 + 摘录) | 默认 | 作用 |
|---|---|---|---|
| `HERMES_TUI_SIDECAR_URL` | `tui_gateway/entry.py:55` 的 `url = os.environ.get("HERMES_TUI_SIDECAR_URL")` | 未设 | 设了就把 `_stdio_transport` 包成 Tee,镜像每一帧到 dashboard `/api/pub` |
| `HERMES_TUI_GATEWAY_SHUTDOWN_GRACE_S` | `tui_gateway/entry.py:79` 的 `raw = (os.environ.get("HERMES_TUI_GATEWAY_SHUTDOWN_GRACE_S") or "").strip()` | 1.0 秒 | 收到终止信号后等自然收尾多久,超时 `os._exit(0)` |
| `HERMES_TUI_GATEWAY_NO_FLUSH` | `tui_gateway/transport.py:58` 的 `_DISABLE_FLUSH = (os.environ.get("HERMES_TUI_GATEWAY_NO_FLUSH", "") or "").strip().lower() in {` | 关 | 写完不 `flush`(半关闭管道上 flush 会阻塞、占着锁饿死整个 worker 池) |

`tui_gateway/server.py` 另有 30 个环境变量读点(`HERMES_TUI_RPC_POOL_WORKERS`、
`HERMES_TUI_SESSION_TTL_S`、`HERMES_TUI_SLASH_TIMEOUT_S`、`HERMES_TUI_WS_ORPHAN_REAP_GRACE_S`、
`TERMINAL_CWD` 等),不在本片穷举范围内(它们大半服务 handler 语义,归其它片)。

---

## §4 端到端链:用户按下 Enter → 屏幕上第一个 token

以 stdio 形态(`hermes --tui`)为主线,逐跳带锚点。**两端**:上游是 Ink(React for CLI)渲染的
终端界面,下游是 `AIAgent` 的 `run_conversation`(属 agent 片,不在此展开)。

```text
[1] 用户在 Ink composer 按 Enter
      ui-tui/src/gatewayClient.ts:764  proc.stdin.write(JSON.stringify({...}) + '\n')
                │  {"jsonrpc":"2.0","id":N,"method":"prompt.submit","params":{"session_id":…,"text":…}}
[2] tui_gateway/entry.py:470   raw = sys.stdin.readline()
[3] tui_gateway/entry.py:483   req = json.loads(line)
[4] tui_gateway/entry.py:491   resp = dispatch(req)
[5] tui_gateway/server.py:1916 bind_transport(t)   ← 本请求期间的写出目标钉死在 contextvar 上
[6] tui_gateway/server.py:1923 method not in _LONG_HANDLERS → 内联 handle_request(req)
[7] tui_gateway/server.py:1897 fn = _methods["prompt.submit"]  ← 已被 method_ctx.install 重绑 __globals__
[8] tui_gateway/methods_prompt.py:130  session["transport"] = t   ← 事件路由的锚
[9] tui_gateway/methods_prompt.py:327  run_thread = threading.Thread(target=..., daemon=True)
[10] tui_gateway/methods_prompt.py:333 return _ok(rid, {"status": "streaming"})  ← 读循环立刻空出来
[11] tui_gateway/entry.py:493  write_json(resp) → 响应回到 Ink,composer 变成「运行中」
--- 以下在 [9] 的那条线程上,与读循环并行 ---
[12] tui_gateway/server.py:9352 _run_prompt_submit(...)
[13] tui_gateway/server.py:9412 record_turn_start(...)  ← 落盘回合标记(§5.7)
[14] tui_gateway/server.py:9622 _emit("message.delta", sid, payload)
[15] tui_gateway/server.py:1539 _emit → _event_frame → write_json
[16] tui_gateway/server.py:1524 事件帧带 session_id → 直接用 _sessions[sid]["transport"]
[17] tui_gateway/transport.py:137 json.dumps(...) + "\n" → _real_stdout.write + flush(锁内)
[18] ui-tui/src/gatewayClient.ts:359  createInterface(proc.stdout).on('line', ...)
[19] ui-tui/src/gatewayClient.ts:362  this.dispatch(JSON.parse(raw))
[20] ui-tui/src/app/createGatewayEventHandler.ts  case 'message.delta' → setState → Ink 重绘
```

跳 [5]/[6] 的原文,`tui_gateway/server.py:1919 @ 863e313`

```
        if isinstance(normalized, dict):
            return normalized

        _rid, method, _params = normalized
        if method not in _LONG_HANDLERS:
            return handle_request(req)

        # Snapshot the context so the pool worker sees the bound transport.
        ctx = contextvars.copy_context()

        def run():
            try:
                resp = handle_request(req)
            except Exception as exc:
                resp = _err(req.get("id"), -32000, f"handler error: {exc}")
            if resp is not None:
                t.write(resp)

        _pool.submit(lambda: ctx.run(run))

        return None
    finally:
```

跳 [14] 的原文,`tui_gateway/server.py:9614 @ 863e313`

```
            def _stream(delta):
                with session["history_lock"]:
                    _append_inflight_delta(session, delta)
                payload = {"text": delta}
                if streamer and (r := streamer.feed(delta)) is not None:
                    payload["rendered"] = r
                if tts_queue is not None and isinstance(delta, str):
                    tts_queue.put(delta)
                _emit("message.delta", sid, payload)
```

跳 [16] 是**整条链上最关键的一跳**——它解释了「为什么后台线程发的事件能找到正确的客户端」。
`tui_gateway/server.py:1511 @ 863e313`

```
def write_json(obj: dict) -> bool:
    """Emit one JSON frame. Routes via the most-specific transport available.

    Precedence:

    1. Event frames with a session id → the transport stored on that session,
       so async events land with the client that owns the session even if
       the emitting thread has no contextvar binding.
    2. Otherwise the transport bound on the current context (set by
       :func:`dispatch` for the lifetime of a request).
    3. Otherwise the module-level stdio transport, matching the historical
       behaviour and keeping tests that monkey-patch ``_real_stdout`` green.
    """
    if obj.get("method") == "event":
        sid = ((obj.get("params") or {}).get("session_id")) or ""
        if sid and (t := (_sessions.get(sid) or {}).get("transport")) is not None:
            return t.write(obj)

```

跳 [8] 的原文——`prompt.submit` 每次都把会话的 transport **重绑到当前客户端**,
这是断线重连后事件还能回到新 socket 的原因。`tui_gateway/methods_prompt.py:126 @ 863e313`

```
    # Re-bind to the current client transport for this request. This keeps
    # streaming events on the active websocket even if an earlier disconnect
    # or fallback moved the session transport to stdio.
    if (t := current_transport()) is not None:
        session["transport"] = t
```

**WS 形态的同一条链**,差异只在两端与合批:

| 跳 | stdio | WebSocket(锚点 + 摘录) |
|---|---|---|
| [2] 收 | `sys.stdin.readline()` | `tui_gateway/ws.py:341` 的 `raw = await ws.receive_text()` |
| [3] 解析 | `json.loads` on 一行 | `tui_gateway/ws.py:360` 的 `req = json.loads(line)` |
| [4] 派发 | 同线程 `dispatch(req)` | `tui_gateway/ws.py:392` 的 `resp = await asyncio.to_thread(server.dispatch, req, transport)` |
| [17] 写 | `+ "\n"` 到 stdout | `tui_gateway/ws.py:237` 的 `await self._ws.send_text(line)`(经合批) |
| [18] 客户端读 | Node 行读器 | `apps/shared/src/json-rpc-gateway.ts:134` 的 `socket.addEventListener('message', message => {` |

---

## §5 逐机制结构笔记

### 5.1 `tui_gateway/entry.py` —— 进程入口

**启动顺序**(模块导入期就做了一半):

| 步 | 锚点 + 摘录 | 做什么 / 为什么 |
|---|---|---|
| 1 | `tui_gateway/entry.py:11` 的 `hermes_bootstrap.harden_import_path()` | 防「用户在含 `utils/`、`proxy/`、`ui/` 目录的路径下启动」时那个目录抢先遮蔽 Hermes 自己的顶层模块。`hermes_bootstrap` 名字够独特,先导入它本身安全。 |
| 2 | `tui_gateway/entry.py:222` 的 `_install_signal("SIGPIPE", signal.SIG_IGN)` | 安装信号处理器:`SIGPIPE`/`SIGINT` → 忽略,`SIGTERM`/`SIGHUP`(Windows 用 `SIGBREAK`)→ `_log_signal`。 |
| 3 | `tui_gateway/entry.py:431` 的 `_install_sidecar_publisher()` | 若设了 `HERMES_TUI_SIDECAR_URL` 就把 `_stdio_transport` 包成 Tee。 |
| 4 | `tui_gateway/entry.py:441` 的 `ensure_mcp_discovery_started()` | MCP 工具发现后台化——一台死的 stdio/http server 会烧掉 1+2+4s 连接重试,即约 7 秒的死气。 |
| 5 | `tui_gateway/entry.py:443` 的 `if not write_json({` | 发 `gateway.ready`;写失败即 `_log_exit` + `sys.exit(0)`。 |
| 6 | `tui_gateway/entry.py:456` 的 `server._ensure_skin_watcher()` | 启动进程唯一的变更监视线程(皮肤 / 宠物 / cron / 会话 / 平台 / 配对)。 |
| 7 | `tui_gateway/entry.py:464` 的 `from hermes_cli.model_switch import prewarm_picker_cache_async` | 在「ready 已发、用户还没打字」这个空窗里预热 `/model` 选择器缓存;发射后不管,一进程一次。 |
| 8 | `tui_gateway/entry.py:469` 的 `while True:` | 进读循环。 |

`tui_gateway/entry.py:443 @ 863e313`

```
    if not write_json({
        "jsonrpc": "2.0",
        "method": "event",
        "params": {
            "type": "gateway.ready",
            # change_events: see tui_gateway/ws.py — clients demote legacy polls.
            "payload": {"skin": resolve_skin(), "change_events": True},
        },
    }):
        _log_exit("startup write failed (broken stdout pipe before first event)")
        sys.exit(0)
```

`change_events: True` 这个字段是**协议协商位**:告诉客户端「后端会主动广播
`pet.changed`/`cron.changed`/`sessions.changed`…,你可以把轮询降级成慢速兜底」。
两条通道都发它(`tui_gateway/entry.py:449` 与 `tui_gateway/ws.py:323` 的
`"payload": {"skin": skin_payload, "change_events": True},`)。

**读循环**,`tui_gateway/entry.py:469 @ 863e313`

```
    while True:
        raw = sys.stdin.readline()
        if not raw:
            # Stdin fell through — check if spurious (O_NONBLOCK flip by a
            # child on the shared open file description) or genuine EOF.
            if not handle_spurious_eof(_recovery_times, _log_exit):
                break
            continue

        line = raw.strip()
        if not line:
            continue

```

**四处崩溃取证设施**——这是本文件最值钱的部分,因为 gateway 死掉时 stdout 是协议管道、
stderr 可能还没冲刷,常规手段留不下任何痕迹:

| 设施 | 锚点 + 摘录 | 治什么 |
|---|---|---|
| 崩溃日志路径 | `tui_gateway/server.py:71` 的 `_CRASH_LOG = os.path.join(_hermes_home, "logs", "tui_gateway_crash.log")` | 所有取证的落点 |
| 主线程未捕获异常 | `tui_gateway/server.py:100` 的 `sys.excepthook = _panic_hook` | 追加完整 traceback + 往 stderr 打一行摘要供 TUI 的 Activity 面板显示 |
| **后台线程**未捕获异常 | `tui_gateway/server.py:103` 的 `def _thread_panic_hook(args):` | 必需的:gateway 大量工作在后台线程上,主线程 excepthook 抓不到它们 |
| 终止信号 | `tui_gateway/entry.py:89` 的 `def _log_signal(signum: int, frame) -> None:` | 把**所有活线程的栈**写进崩溃日志——`SIGPIPE` 默认处置会在任意后台线程(TTS 播放、提示音、语音状态发射器)写向已停读的 stdout 时静默杀死进程,内核先收尸,解释器一行都跑不到 |
| 退出原因 | `tui_gateway/entry.py:233` 的 `def _log_exit(reason: str) -> None:` | 四条退出路径全汇入这里,否则 TUI 只显示「gateway exited」而无线索 |

**终止语义的取舍**:朴素的 `sys.exit(0)` 会和 worker 池竞争——一条持有 `_stdout_lock`
正在 flush 的线程能让解释器收尾无限期挂着。现在的做法是三层:

| 层 | 锚点 + 摘录 | 作用 |
|---|---|---|
| 问题声明 | `tui_gateway/entry.py:100` 的 `Termination semantics: ``sys.exit(0)`` here used to race the worker` | docstring 自陈这条竞争 |
| 硬退出兜底 | `tui_gateway/entry.py:145` 的 `timer = _threading.Timer(_shutdown_grace_seconds(), _hard_exit)` | 守护 `Timer`,默认 1s(`HERMES_TUI_GATEWAY_SHUTDOWN_GRACE_S` 可调)后 `os._exit(0)` |
| 显式落盘 | `tui_gateway/entry.py:158` 的 `_shutdown_sessions()` | 不等 atexit,直接把未落盘消息写进 state.db |

**`_install_signal` 的线程守卫**:`signal.signal()` 只能在主线程调。
桌面 / WebSocket 路径上 `server._build()` 跑在守护线程里,它会
`from tui_gateway.entry import ensure_mcp_discovery_started` —— 这是该进程里 `entry` 的**首次导入**,
于是模块级的信号安装在非主线程执行,原来会抛
`ValueError: signal only works in main thread` 把 MCP 发现整个搞崩。
现在非主线程直接静默跳过(`tui_gateway/entry.py:209` 的
`if threading.current_thread() is not threading.main_thread():`):
信号处理器是进程全局的,任何一次主线程导入都已经替所有人装好了。

**MCP 发现的三个函数有个共同结构:两个独立的发现线程 owner。**
stdio 的 `hermes --tui` 在本模块起自己的线程,桌面 App + dashboard 的 WS sidecar 与
`hermes dashboard` 则经 `hermes_cli.mcp_startup.start_background_mcp_discovery` 起。

| 函数 | 锚点 + 摘录 | 用途 |
|---|---|---|
| 等待(有界) | `tui_gateway/entry.py:255` 的 `def wait_for_mcp_discovery(timeout: "float | None" = None) -> None:` | 首次 agent 构建前有界 join,让「已在启动的快 server」赶上工具快照,同时不重新引入启动卡顿 |
| 在飞查询 | `tui_gateway/entry.py:315` 的 `def mcp_discovery_in_flight() -> bool:` | 决定是否安排「迟到的工具快照刷新」;**必须查两个 owner**——只查 entry 那条线程曾让桌面/dashboard 完全没有迟到刷新,慢 MCP server 的工具整场会话不出现 |
| 等待(可长) | `tui_gateway/entry.py:346` 的 `def join_mcp_discovery(timeout: float | None = None) -> bool:` | 非关键路径的迟到刷新等待者,可接受长等并报告结果 |

### 5.2 `tui_gateway/transport.py` —— 传输抽象

**抽象只有两个方法**:`write(obj) -> bool` 与 `close()`。`write` 的返回值是**协议级信号**,
不是「成功/失败」:`False` **只**表示「对端没了」。
`Transport` 是 `typing.Protocol` + `@runtime_checkable`(`tui_gateway/transport.py:66` 的
`@runtime_checkable`),即结构化子类型——`StdioTransport`、`TeeTransport`、`WSTransport`、
`WsPublisherTransport`、`_DropTransport` 谁都不继承它。

**「对端没了」与「主机 I/O 真出问题」的分诊**,这是本文件的核心设计。
`tui_gateway/transport.py:36 @ 863e313`

```
_PEER_GONE_ERRNOS = frozenset({
    errno.EPIPE,        # write to closed pipe (POSIX)
    errno.ECONNRESET,   # peer reset the connection
    errno.EBADF,        # fd closed under us
    errno.ESHUTDOWN,    # transport endpoint shut down
    getattr(errno, "WSAECONNRESET", -1),  # win32 mapping (no-op on POSIX)
    getattr(errno, "WSAESHUTDOWN", -1),
} - {-1})
```

`getattr(..., -1)` + `- {-1}` 是个小手法:POSIX 上没有 `WSAECONNRESET`,取默认 `-1` 再从集合里减掉,
于是同一份代码在两个平台上都得到正确的集合,不用 `if sys.platform`。

分诊规则,`tui_gateway/transport.py:143 @ 863e313`

```
            except BrokenPipeError:
                return False
            except ValueError as e:
                # ValueError("I/O operation on closed file") is the
                # ONLY ValueError that means "peer gone".  Anything
                # else — including UnicodeEncodeError, which is a
                # ValueError subclass for misconfigured locales —
                # is a real bug; re-raise so it surfaces in the crash log.
                if isinstance(e, UnicodeEncodeError) or "closed file" not in str(e):
                    raise
                return False
            except OSError as e:
                if e.errno not in _PEER_GONE_ERRNOS:
                    raise
                logger.debug("StdioTransport write peer gone: %s", e)
                return False
```

**为什么必须这么严**(`tui_gateway/transport.py:117` 的
`Returning ``False`` is the dispatcher's "broken stdout pipe" signal`):`entry.py` 见到
`write_json` 返回 `False` 就 `sys.exit(0)`。如果编程错误(不可 JSON 化的 payload、
locale 配错导致的 `UnicodeEncodeError`、`ENOSPC` 之类的主机故障)也走 `False`,
一个真 bug 会长得像干净的断连,崩溃日志里什么都没有。

**其余四个设计点**:

| 设计点 | 锚点 + 摘录 | 说明 |
|---|---|---|
| 序列化在锁外、写入在锁内 | `tui_gateway/transport.py:137` 的 `line = json.dumps(obj, ensure_ascii=False) + "\n"` | 大 payload 的 `json.dumps` 不占锁,否则一条大帧挡住其他线程发自己的帧 |
| flush 的第三态:**挂住** | `tui_gateway/transport.py:58` 的 `_DISABLE_FLUSH = (os.environ.get("HERMES_TUI_GATEWAY_NO_FLUSH", "") or "").strip().lower() in {` | 半关闭管道上 flush 会一直占着锁,锁内解决不了,所以留了环境变量逃生舱;但注释同时警告:接管道的 Python 文本 stdout 是全缓冲的,不配 `-u`/`PYTHONUNBUFFERED=1` 就关 flush,帧会攒在缓冲里、TUI 永远等不到 `gateway.ready` |
| contextvar 而非 thread-local | `tui_gateway/transport.py:90` 的 `def bind_transport(transport: Optional[Transport]):` | handler 会被丢到线程池上跑,`dispatch` 用 `contextvars.copy_context()` 快照后 `ctx.run(run)`,绑定跟着走过去;thread-local 做不到 |
| 用 callable 取流而不是存流 | `tui_gateway/transport.py:111` 的 `self._stream_getter = stream_getter` | 为了让测试里的 `monkeypatch.setattr(server, "_real_stdout", ...)` 继续生效——「为可测性付出的一点间接层」的一个具体样本 |

**`TeeTransport` 的语义是不对称的**:主 sink 的返回值和异常决定结果,从 sink 的失败全部吞掉。
用途是 PTY 子进程——每一帧既要落在 Ink 的 stdio 上,也要落在喂 dashboard 侧边栏的反向 WS 上,
而侧边栏卡住绝不能拖住 agent 主循环。写入顺序是**主先从后**。
`tui_gateway/transport.py:201 @ 863e313`

```
    def write(self, obj: dict) -> bool:
        # Primary first so a slow sidecar (WS publisher) never delays Ink/stdio.
        ok = self._primary.write(obj)
        for sec in self._secondaries:
            try:
                sec.write(obj)
            except Exception:
                pass
        return ok
```

### 5.3 `tui_gateway/ws.py` —— WebSocket 通道与逐 token 合批

**`WSTransport.write` 要解决的问题**:它被**worker 线程**调用,而 socket 属于事件循环线程。
所以 `write` 必须把活儿投递到 loop 上。三条分支:

1. **流式帧**(token):进缓冲区 + 装一个 33ms 定时器,立即返回。
2. **非流式帧 + 不在 loop 线程**:`safe_schedule_threadsafe` 投递,然后
   `fut.result(timeout=10)` 等落地。
3. **非流式帧 + 在 loop 线程**(`handle_ws` 自己的内联响应):`create_task` 发射后不管——
   否则就是「把活儿排到自己正在阻塞的那个 loop 上」,必然死锁。

**合批的动机与安全性**,`tui_gateway/ws.py:53 @ 863e313`

```
_STREAMING_EVENT_TYPES = frozenset({
    "message.delta",
    "reasoning.delta",
    "thinking.delta",
})
# Max time a streamed token waits in the buffer before flush (~30 fps). Short
# enough to stay imperceptible to the live token cadence.
_TOKEN_COALESCE_S = 0.033
```

一次模型回复会爆出几百个 token 帧,每一帧都是一次 loop 唤醒,和正在跑的 agent turn 抢 GIL
(GIL = Python 全局解释器锁,同一时刻只有一条线程执行字节码)。合批把这个抖动压掉。
**只有「纯展示、可延迟 33ms」的三种事件进这个集合**,任何客户端必须及时看到的帧
(工具 / 审批 / 状态 / 完成)都是非流式的,而非流式帧会**先把缓冲区清空再排自己**,
所以线序不会乱。

`tui_gateway/ws.py:134 @ 863e313`

```
        if self._is_streaming_frame(obj):
            with self._token_lock:
                self._pending_tokens.append(line)
                if not self._token_flush_armed:
                    self._token_flush_armed = True
                    # call_soon_threadsafe arms the call_later timer on the loop
                    # thread and is safe to call from a worker or the loop.
                    self._loop.call_soon_threadsafe(self._arm_token_flush)
            return not self._closed
```

**两把锁,各管一件事**:

| 锁 | 锚点 + 摘录 | 管什么 |
|---|---|---|
| `_token_lock` | `tui_gateway/ws.py:101` 的 `self._token_lock = threading.Lock()` | 缓冲区 + armed 标志,对抗 worker 线程 |
| `_send_lock` | `tui_gateway/ws.py:108` 的 `self._send_lock = asyncio.Lock()` | 多个批次在 loop 上串行落到 socket 上(loop 从卡顿恢复时可能同时排着好几批) |

「排入 send 的动作放在 `_token_lock` 里面」是为了让**在线序 == 缓冲序**,
即使合批定时器和非流式 flush 同一瞬间触发(`tui_gateway/ws.py:147` 的
`# scheduled INSIDE the lock so the on-the-wire order matches the buffer`)。

**loop 卡顿不等于 socket 死了**,`tui_gateway/ws.py:165 @ 863e313`

```
        try:
            fut.result(timeout=_WS_WRITE_TIMEOUT_S)
            return not self._closed
        except concurrent.futures.TimeoutError:  # builtin TimeoutError on 3.11+
            # The event loop is stalled (GIL-heavy agent turn, delegation
            # running N children), NOT the socket dead. The send coroutine is
            # already scheduled and will flush once the loop breathes — latching
            # _closed here permanently silenced live windows after one slow
            # write (the "subagent window shows zero streaming" bug). Unblock
            # the worker thread and keep the transport alive; _safe_send_many
            # latches on a real socket error when the frame actually fails.
            _log.warning(
                "ws write slow (loop stalled >%ss) peer=%s — frame left in flight",
                _WS_WRITE_TIMEOUT_S, self._peer,
            )
            return not self._closed
```

**事故经过**:委派(delegation)一次跑 N 个子代理,GIL 被压住,事件循环卡住 >10s;
一次超时就把 `_closed` 置位,此后这个 transport **永久静默**——用户看到的现象是
「子代理窗口一个 token 都不流」。修法是:超时只放开 worker 线程、保留 transport 活性,
真的 socket 错误由 `_safe_send_many` 在写失败时置位
(`tui_gateway/ws.py:242` 的 `self._closed = True`)。
**注意:模块顶部的注释还是旧版说法,见 §6 ▲-2。**

**`handle_ws` 的生命周期**:

| 阶段 | 锚点 + 摘录 | 做什么 |
|---|---|---|
| 入口 | `tui_gateway/ws.py:286` 的 `async def handle_ws(ws: Any) -> None:` | 一次连接一次调用 |
| accept | `tui_gateway/ws.py:297` 的 `await ws.accept()` | 接受连接 |
| 调优 | `tui_gateway/ws.py:301` 的 `_disable_nagle(ws)` | 关 Nagle(`TCP_NODELAY`),否则内核把小 token 帧攒成一坨,模型「思考停顿」后的爆发会一 tick 落到客户端,任何客户端侧平滑都救不回节奏 |
| 建 transport | `tui_gateway/ws.py:304` 的 `transport = WSTransport(ws, asyncio.get_running_loop(), peer=peer)` | 一连接一 transport |
| 冷启动避让 | `tui_gateway/ws.py:313` 的 `skin_payload = await asyncio.to_thread(server.resolve_skin)` | `resolve_skin` 读配置 + 初始化皮肤引擎(同步 I/O + CPU),放线程池以免堵住 WS 读循环 |
| 握手 | `tui_gateway/ws.py:314` 的 `ready_ok = await transport.write_async(` | 发 `gateway.ready` |
| 注册 | `tui_gateway/ws.py:332` 的 `server.register_live_transport(transport)` | 登记进全局广播名册(无 sid 的 `skin.changed` 等靠它才送得到) |
| 读循环 | `tui_gateway/ws.py:339` 的 `while True:` | receive → parse → 派发 → 写响应 |
| 拆除 | `tui_gateway/ws.py:433` 的 `server.unregister_live_transport(transport)` | 注销名册 → `transport.close()` → 释放唤醒词归属 → 回收/剥离会话 → `ws.close()` → 打一行统计 |

**读循环是串行的**(`tui_gateway/ws.py:392` 的
`resp = await asyncio.to_thread(server.dispatch, req, transport)`):每条请求都 `await`,
所以**内联** handler 会挡住同一 socket 上的下一条 RPC。这不是疏漏而是已知取舍:
修法是把前端会轮询的 RPC 全部塞进 `_LONG_HANDLERS`,让 `dispatch` 立刻返回 `None`。
这条不变量被钉成了断言:`tests/tui_gateway/test_inline_rpc_gil_starvation.py:92` 的
`assert method in server._LONG_HANDLERS, (`,以及
`tests/tui_gateway/test_inline_rpc_gil_starvation.py:139` 的
`assert server._rpc_pool_workers >= 8, (`。

**拆除路径故意全部走线程池**(`tui_gateway/ws.py:454` 的
`reaped_sessions, detached_sessions = await asyncio.to_thread(`):
`_close_session_by_id` 会做阻塞的 `worker.close()`(终止子进程 + 等待)加一次同步 DB 写,
内联的话会把 uvicorn 的事件循环冻住,连带冻住这台机器上**其它所有**活连接。

**断连后会话不立即销毁**,`tui_gateway/server.py:1084 @ 863e313`

```
    with _sessions_lock:
        owned = [(sid, s) for sid, s in _sessions.items() if s.get("transport") is transport]
    reaped = 0
    detached = 0
    for sid, session in owned:
        if session.get("close_on_disconnect"):
            _close_session_by_id(sid, end_reason=end_reason)
            reaped += 1
        else:
            # Point detached sessions at the drop sentinel (NOT real stdio) so
            # _ws_session_is_orphaned recognizes them and the grace-reap can
            # actually fire; a standalone `hermes --tui` keeps real _stdio.
            session["transport"] = _detached_ws_transport
            detached += 1
```

**为什么换成丢弃 sink 而不是 stdio**(`tui_gateway/server.py:320` 的
`# Detached websocket sessions use a drop sink instead of stdio. Desktop embeds`):
桌面 App 把 gateway 嵌在自己进程里、并把 stdout 收进日志,过期的 JSON-RPC 帧掉到那儿会污染日志。

### 5.4 `tui_gateway/event_publisher.py` —— 旁路扇出

**扇出模型:不是多客户端广播,而是「单向、单连接、best-effort 镜像」。**
回答派工书的三问:

| 问 | 答 | 锚点 + 摘录 |
|---|---|---|
| 多客户端? | **否**,一个实例一个 URL 一个 WS | `tui_gateway/event_publisher.py:41` 的 `__slots__ = ("_url", "_lock", "_ws", "_dead", "_q", "_worker")` |
| 真正的多客户端扇出在哪 | 在 server.py 的名册 + 遍历广播 | `tui_gateway/server.py:1547` 的 `_live_transports: set[Transport] = set()` 与 `tui_gateway/server.py:1565` 的 `def _broadcast_global_event(event: str, payload: dict | None = None) -> None:` |
| 背压? | **有界丢弃,不阻塞** | `tui_gateway/event_publisher.py:37` 的 `_QUEUE_MAX = 256`;`write` 用 `put_nowait`,`queue.Full` 直接返回 `False` |
| 真正的 send 在哪 | 守护线程,入队即返回 | `tui_gateway/event_publisher.py:66` 的 `target=self._drain,` |
| 丢事件 ①:库没装 | 直接标死 | `tui_gateway/event_publisher.py:51` 的 `if ws_connect is None:` |
| 丢事件 ②:连接失败 | 标死,回落 stdio-only | `tui_gateway/event_publisher.py:58` 的 `_log.debug("event publisher connect failed: %s", exc)` |
| 丢事件 ③:运行中 send 失败 | 标死并短路后续全部写 | `tui_gateway/event_publisher.py:86` 的 `_log.debug("event publisher write failed: %s", exc)` |

失败模式是**设计声明**而非疏漏,`tui_gateway/event_publisher.py:14 @ 863e313`

```
Failure mode: silent.  The agent loop must never block waiting for the
sidecar to drain.  A dead WS short-circuits all subsequent writes.
Actual ``send`` calls run on a daemon thread so the TeeTransport's
``write`` returns after enqueueing (best-effort; drop when the queue is full).
```

**多客户端广播的那一边**——注意它对「一个卡住的 peer」的处理:
`tui_gateway/server.py:1572 @ 863e313`

```
    with _live_transports_lock:
        targets = list(_live_transports)

    if not targets:
        _emit(event, "", payload)
        return

    frame = _event_frame(event, "", payload)
    for transport in targets:
        try:
            transport.write(frame)
        except Exception:
            # One wedged peer must not stall the rest; disconnect teardown
            # unregisters it.
            logger.debug("global-event broadcast write failed type=%s", event, exc_info=True)
```

**它为什么存在**:dashboard 的 `/api/pty` 会 spawn 一个 `hermes --tui` 子进程,
那个子进程再 spawn 它自己的 `tui_gateway.entry`。工具 / 推理 / 状态事件发在**那个** gateway 的
transport 上,离 dashboard 服务进程隔了三层。要让侧边栏看见,只能由 PTY 侧 gateway
主动反向连回 dashboard。完整链路:

| 跳 | 锚点 + 摘录 |
|---|---|
| PTY 侧 gateway 发 | `tui_gateway/event_publisher.py:84` 的 `self._ws.send(item)  # type: ignore[union-attr]` |
| dashboard 收并重播 | `hermes_cli/web_server.py:15897` 的 `await _broadcast_event(ws.app, channel, await ws.receive_text())` |
| 浏览器侧消费 | `web/src/components/ChatSidebar.tsx:356` 的 `if (frame.method !== "event" || !frame.params) {` |

### 5.5 `tui_gateway/_stdin_recovery.py` —— 化石一号:子进程翻标志位导致的假 EOF

**故障的因果经过**,`tui_gateway/_stdin_recovery.py:3 @ 863e313`

```
When a child process inherits fd 0 (stdin) and sets ``O_NONBLOCK``, the flag
lands on the **shared open file description** — not just the child's descriptor.
The gateway's next ``read()`` returns ``EAGAIN``, which CPython's buffered
``TextIOWrapper`` converts to ``b''`` (apparent EOF), killing the gateway.
```

拆成读者能复述的形状:

1. **什么输入**:gateway 起了一个子进程(slash worker、shell 工具、任何 `subprocess`)。
   子进程继承了 fd 0。某个库为了做非阻塞 I/O,对 fd 0 调 `fcntl(F_SETFL, O_NONBLOCK)`。
2. **为什么会伤到父进程**:POSIX 里 `O_NONBLOCK` 这类**文件状态标志**不挂在描述符上,
   挂在**共享的 open file description** 上。`fork`/`dup` 出来的描述符指向同一个 description,
   所以子进程翻的标志,父进程立刻看得见。
3. **什么现象**:gateway 主循环里的 `sys.stdin.readline()` 底下的 `read()` 返回 `EAGAIN`。
   CPython 的缓冲 `TextIOWrapper` 把 `EAGAIN` 翻译成 `b''`。
   而 `b''` 在读循环里的语义是**「对端关闭了」**。于是 `entry.py` 走 `break` → 进程退出 →
   TUI 显示「gateway exited」,而 TUI 那头什么也没做。
4. **怎么修**:空 `readline()` 不再无条件当 EOF。先查标志位:
   `O_NONBLOCK` 是清的 → 真 EOF,照旧退出;是置位的 → 假 EOF,清掉它然后 `continue`。

`tui_gateway/_stdin_recovery.py:114 @ 863e313`

```
    # Spurious EOF: a child set ``O_NONBLOCK`` (and/or ``SO_RCVTIMEO``) on
    # the shared file description, laundered into ``b''`` / ``EAGAIN`` by
    # CPython's buffered layer.  Restore blocking mode and resume.
    now = time.time()
    recovery_times.append(now)
    recovery_times[:] = [t for t in recovery_times if t > now - 60]
    if len(recovery_times) > MAX_RECOVERIES_PER_MINUTE:
        log_fn(  # type: ignore[operator]
            f"stdin spurious-EOF recovery rate exceeded "
            f"({len(recovery_times)}/min, cap {MAX_RECOVERIES_PER_MINUTE})"
        )
        return False

    diag = diagnose_stdin_state()
    log_fn(f"stdin spurious EOF (subprocess O_NONBLOCK flip), recovering: {diag}")  # type: ignore[operator]

    # Clear ``O_NONBLOCK`` on the shared file description.
    os.set_blocking(0, True)
```

**三个补丁细节都是被现实教出来的**:

| 细节 | 锚点 + 摘录 | 治什么 |
|---|---|---|
| 速率上限 10 次/分钟 | `tui_gateway/_stdin_recovery.py:45` 的 `MAX_RECOVERIES_PER_MINUTE = 10` | 一个疯狂翻标志的子进程会让「假 EOF → 恢复 → 假 EOF」变成烧 CPU 的紧循环;超限就退出,让父进程用干净状态重启,比永远打下去安全 |
| 顺带清 `SO_RCVTIMEO` | `tui_gateway/_stdin_recovery.py:142` 的 `s.setsockopt(_socket.SOL_SOCKET, _socket.SO_RCVTIMEO, struct.pack("ll", 0, 0))` | 这是 socket 选项而非文件状态标志,同样共享在 open file description 上;子进程设了它会让下一次 `readline()` **超时返回 `''`** 而 `O_NONBLOCK` 是**清的**,于是恢复逻辑判成真 EOF、或一路超时循环到撞上速率上限 |
| POSIX-only | `tui_gateway/_stdin_recovery.py:99` 的 `if not (_HAS_FCNTL and _fcntl is not None):` | 没有 `fcntl`(Windows)就直接报真 EOF;Windows 上共享 description 的 `O_NONBLOCK` 不成立 |

**`diagnose_stdin_state` 用 `socket.fromfd(0, AF_UNIX, SOCK_STREAM)` 探 fd 0**:
fd 0 是管道时 `getsockopt` 会抛 `ENOTSOCK`,被外层 `except Exception: pass` 吞掉;
`fromfd` 复制出来的 fd 由内层 `finally` 释放,不碰原始 fd 0
(`tui_gateway/_stdin_recovery.py:75` 的 `# ``fromfd`` duped the fd; ``close`` releases the dup without`)。

**两个调用方**(共用此模块的理由):`tui_gateway/entry.py:474` 的
`if not handle_spurious_eof(_recovery_times, _log_exit):` 与 `tui_gateway/slash_worker.py:157` 的
`if not handle_spurious_eof(_sw_recovery_times, _sw_log):`(后者属别的片)。
两者各持自己的 `recovery_times` 列表并传入自己的 `log_fn`,所以模块本身不持状态。

### 5.6 `tui_gateway/loop_noise.py` —— 化石二号:对端硬断导致的回溯洪水

**故障的因果经过**,`tui_gateway/loop_noise.py:3 @ 863e313`

```
When the Desktop client forcibly closes its WebSocket while the gateway still
has pending socket operations, asyncio's transport teardown logs a full
traceback for every pending ``_call_connection_lost`` callback. On Windows this
surfaces as ``ConnectionResetError: [WinError 10054]`` (and the rarer
``ConnectionAbortedError: [WinError 10053]``); on POSIX it is the equivalent
``ConnectionResetError``/``BrokenPipeError``. A single client disconnect can
emit 50+ identical tracebacks into ``errors.log`` (#50005).
```

1. **什么输入**:桌面客户端**强制**关掉自己的 WebSocket,而 gateway 这边还有未完成的 socket 操作。
2. **什么现象**:asyncio 的 transport 拆除逻辑为**每一个**待处理的 `_call_connection_lost`
   回调打一整份 traceback,一次断连能往 `errors.log` 里灌 50+ 份一模一样的 traceback。
3. **为什么不可操作**:这就是「对端在我们的写排空之前挂了」的预期副作用,没有任何可修的东西。
4. **怎么修**:链一个 loop 异常处理器,**只**把这一类折叠成一行 debug,其余原样转给原处理器。

**「只这一类」是靠双重门控做到的**,`tui_gateway/loop_noise.py:44 @ 863e313`

```
    if not isinstance(exc, _BENIGN_TEARDOWN_ERRORS):
        return False
    # The flood originates from the transport's connection-lost callback. Match
    # on its repr so we don't suppress the same error type raised elsewhere.
    callback = context.get("callback")
    handle = context.get("handle")
    marker = "_call_connection_lost"
    return marker in repr(callback) or marker in repr(handle)
```

异常类型对了**还不够**——必须同时是从 transport 的 connection-lost 回调里冒出来的。
判据是对 `callback` / `handle` 取 `repr` 后找 `"_call_connection_lost"` 这个子串。
**取舍**:靠 repr 匹配是脆的(CPython 改了内部回调名就失效),但换来的是
「同类异常在真正的 handler 里抛出时不会被吞」。这是「宁可漏抓噪音,不可漏抓真 bug」的选择。

**链式安装 + 幂等**:

| 机制 | 锚点 + 摘录 |
|---|---|
| 入口 | `tui_gateway/loop_noise.py:54` 的 `def install_loop_noise_filter(loop: asyncio.AbstractEventLoop) -> None:` |
| 先存旧处理器 | `tui_gateway/loop_noise.py:63` 的 `previous = loop.get_exception_handler()` |
| 不匹配就转出去 | `tui_gateway/loop_noise.py:73` 的 `previous(loop, context)` |
| 没有旧处理器就转默认 | `tui_gateway/loop_noise.py:75` 的 `loop.default_exception_handler(context)` |
| 幂等标记 | `tui_gateway/loop_noise.py:81` 的 `loop._hermes_noise_filter_installed = True  # type: ignore[attr-defined]` |

打在 loop 实例上的标记让重复安装成为 no-op,这样每次重连 / 每次进 serve 都可以无脑调一遍,
不会把处理器叠成一串。

### 5.7 `tui_gateway/turn_marker.py` —— 回合标记解决什么同步问题

**问题的形状**,`tui_gateway/turn_marker.py:3 @ 863e313`

```
A running turn's progress lives only in process memory (the agent flushes to
SQLite at turn end, not mid-turn), so an app/backend/machine death mid-turn
leaves no durable trace of the interrupted prompt. This sidecar is that
trace: a marker is written when a turn starts running and cleared when the
turn concludes — success, handled error, or interrupt all clear it, so only
a process death leaves one behind. ``session.resume`` reads the marker to
decide whether to auto-continue the interrupted turn (see
``_maybe_schedule_auto_continue`` in ``tui_gateway/server.py``).
```

即:一个正在跑的 turn,它的进度**只存在于进程内存里**——agent 是在 turn **结束时**
才把消息刷进 SQLite。于是「App / 后端 / 机器在 turn 中途死掉」这件事**不留任何持久痕迹**:
数据库里没有那条用户消息,客户端也没收到任何终结帧。用户看到的是「我明明发过一句话,它消失了」。
**这就是一个跨进程重启的同步问题**:内存态的「turn 正在跑」这个事实,
需要一个**落盘的、能在进程死后被读到的**投影。

**协议只有三步**:

| 时机 | 模块侧(锚点 + 摘录) | 调用侧(锚点 + 摘录) |
|---|---|---|
| turn 即将开跑 | `tui_gateway/turn_marker.py:97` 的 `def record_turn_start(` | `tui_gateway/server.py:9412` 的 `record_turn_start(marker_home, marker_key, marker_text, attempts=marker_attempt)` |
| turn 有了任何结局 | `tui_gateway/turn_marker.py:124` 的 `def clear_turn_marker(home: Path | str, session_key: str) -> None:` | `tui_gateway/server.py:7211` 的 `def _retire_turn_marker(session: dict, *keys: str) -> None:`,三个调用点 `server.py:7625`/`9869`/`10102` |
| `session.resume` 冷路径 | `tui_gateway/turn_marker.py:140` 的 `def read_turn_marker(home: Path | str, session_key: str) -> dict[str, Any] | None:` | `tui_gateway/server.py:7252` 的 `marker = read_turn_marker(home, session_key)` |

**关键不变量**:成功、被处理的错误、被打断——**三种结局都清标记**。
所以「标记还在」= 「进程死了」,这是个**正证据**,不是启发式猜测。

**清标记的时机被特意提前了**,`tui_gateway/server.py:7212 @ 863e313`

```
    """Drop the crash marker for a turn whose outcome is about to reach the client.

    Called immediately before the terminal frame rather than at the end of the
    turn thread: post-turn work (titles, memory sync, goal hooks) runs for a
    second or more after the client has its answer, and quitting inside that
    window would leave a marker that looks like a crash — re-running a finished
    turn on the next launch. Extra ``keys`` cover a session_key that
    compression rotated mid-turn.
    """
```

**其余四个设计点**:

| 设计点 | 锚点 + 摘录 | 说明 |
|---|---|---|
| 文件有界 | `tui_gateway/turn_marker.py:36` 的 `_MAX_AGE_SECS = 24 * 3600` 与 `tui_gateway/turn_marker.py:37` 的 `_MAX_ENTRIES = 32` | 一串倒霉的连续崩溃不能把这个 sidecar 撑爆;每次写都先 `_prune` |
| prompt 截断 | `tui_gateway/turn_marker.py:40` 的 `_MAX_PROMPT_CHARS = 64_000` | 一次病态的几兆粘贴不该被逐 turn 记账 |
| 原子落盘 | `tui_gateway/turn_marker.py:84` 的 `fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".turn-marker-")` 与 `tui_gateway/turn_marker.py:88` 的 `os.replace(tmp, path)` | 同目录临时文件 + rename;空字典时直接 `unlink(missing_ok=True)`,不留空文件 |
| 全部 best-effort | `tui_gateway/turn_marker.py:17` 的 `Every function is best-effort by design — marker bookkeeping must never` | I/O 错误降级成「没有标记」而不是抛出 |
| `session_key` 会被压缩轮换 | `tui_gateway/server.py:9406` 的 `# session_key mid-turn, so remember the key we wrote under.` | 所以 `_retire_turn_marker(session, *keys)` 接受额外的 key |

**自动续跑的三道闸**,`tui_gateway/server.py:7255 @ 863e313`

```
    enabled, freshness_secs, max_attempts = _auto_continue_config()
    age = time.time() - marker["started_at"]
    if not enabled or age > freshness_secs or marker["attempts"] >= max_attempts:
```

默认值分别是 True / 15 分钟 / 2 次
(`tui_gateway/server.py:7181` 的 `_AUTO_CONTINUE_ENABLED_DEFAULT = True`、
`tui_gateway/server.py:7182` 的 `_AUTO_CONTINUE_FRESHNESS_MINUTES_DEFAULT = 15`、
`tui_gateway/server.py:7183` 的 `_AUTO_CONTINUE_MAX_ATTEMPTS_DEFAULT = 2`)。
第三道是**崩溃循环断路器**:`attempts` 字段被写回标记,下次 resume 读回来,
达到上限就清标记不再试(`tui_gateway/turn_marker.py:102` 的
`` ``attempts`` counts how many auto-continues led to this run: 0 for a ``)。

### 5.8 `tui_gateway/method_ctx.py` —— 把 handler 搬出 14K 行模块而不改一行 handler 体

**问题**,`tui_gateway/method_ctx.py:3 @ 863e313`

```
server.py's ~130 JSON-RPC handlers close over its module globals
(``_sessions``, ``_ok``, ``_err``, config helpers, ...).  To move them
out of the 19K-line module without rewriting a single handler body,
each ``methods_*`` module defines its handlers under a local
:class:`HandlerRegistry` and server.py calls :meth:`HandlerRegistry.install`
at the end of its own import, once every global the handlers close over
exists.  ``install()`` rebinds each handler's ``__globals__`` to
server.py's namespace with ``types.FunctionType``, so handler bodies
stay byte-identical and ``global X`` statements inside handlers keep
mutating server.py state exactly as before the split.
```

**解法:不改 handler,改它的 `__globals__`。**
`tui_gateway/method_ctx.py:41 @ 863e313`

```
    def install(self, server) -> None:
        """Rebind pending handlers onto ``server``'s globals and register them."""
        g = vars(server)
        for name, fn in self._pending:
            real = types.FunctionType(
                fn.__code__, g, fn.__name__, fn.__defaults__, fn.__closure__
            )
            real.__kwdefaults__ = fn.__kwdefaults__
            real.__doc__ = fn.__doc__
            real.__dict__.update(fn.__dict__)
            if getattr(fn, "_hermes_profile_scoped", False):
                real = server._profile_scoped(real)
            server._methods[name] = real
```

`types.FunctionType(code, globals, ...)` 用**同一份已编译的 `__code__`** 造一个新函数对象,
只把 `globals` 换成 `vars(server)`。于是:handler 体的字节码一字未动;
里面读 `_sessions` 读到的是 server.py 的 `_sessions`;里面 `global _foo` 改的也是 server.py 的 `_foo`。

**配套的三件事**:

| 件 | 锚点 + 摘录 | 说明 |
|---|---|---|
| `@method` 的替身 | `tui_gateway/method_ctx.py:27` 的 `def method(self, name: str):` | 只把 `(name, fn)` 攒进 `_pending`,不注册 |
| `@_profile_scoped` 的替身 | `tui_gateway/method_ctx.py:36` 的 `def profile_scoped(self, fn):` | 只打一个 `_hermes_profile_scoped` 标记;真装饰器 `tui_gateway/server.py:1406` 的 `def _profile_scoped(handler):` 住在 server.py,所以只能在 `install` 里补上 |
| 无循环导入 | `tui_gateway/method_ctx.py:14` 的 `No import cycle: ``methods_*`` modules never import server at module` | 是 server 导入它们并把自己传进 `register()` |

**导入时机必须在模块末尾**,`tui_gateway/server.py:13987 @ 863e313`

```
# ── Split @method handler modules (see method_ctx.py) ────────────────
# Imported at the end of this module so every global the handlers close
# over already exists; register() rebinds them onto this namespace.
from . import (  # noqa: E402
    methods_complete as _methods_complete,
    methods_config as _methods_config,
    methods_prompt as _methods_prompt,
    methods_session as _methods_session,
    methods_tools as _methods_tools,
)

for _m in (
    _methods_session,
    _methods_prompt,
    _methods_config,
    _methods_complete,
    _methods_tools,
):
    _m.register(sys.modules[__name__])
del _m
```

**取舍要说清**:这是一次**机械搬迁**(docstring 第一行自称 "mechanical move"),
换来的是「14K 行文件不必一次性重构」和「handler 体零风险」;代价是
**静态分析工具与人类读者都会在 `methods_*.py` 里看到一堆看不出来源的自由变量**
(读 `methods_session.py` 时 `_sessions` 从哪来是不可见的),
而且模块级导入顺序变成了正确性的一部分(挪一行 import 就会 `NameError`)。

### 5.9 `tui_gateway/render.py` —— 渲染桥(本基线上是死的)

三个函数同构:试着 import `agent.rich_output` 的对应符号,失败返回 `None`;
成功则调用,先试带 `cols=` 的新签名,`TypeError` 就退回不带 `cols` 的旧签名,
其它异常一律 `None`。`tui_gateway/render.py:10 @ 863e313`

```
def render_message(text: str, cols: int = 80) -> str | None:
    try:
        from agent.rich_output import format_response
    except ImportError:
        return None

    try:
        return format_response(text, cols=cols)
    except TypeError:
        return format_response(text)
    except Exception:
        return None
```

`except TypeError: return format_response(text)` 是「同时兼容两个签名」的写法,
代价是 `format_response` 内部**任何**由参数不匹配引发的 `TypeError` 都会导致函数被调第二次。

四个调用点,在本基线上**全部走 `None` 分支**(见 §6 ■-1):

| 调用点(锚点 + 摘录) | 场景 |
|---|---|
| `tui_gateway/server.py:7620` 的 `rendered = render_message(text, cols)` | 终结错误帧的正文渲染 |
| `tui_gateway/server.py:9457` 的 `streamer = make_stream_renderer(cols)` | 每 turn 一次,建流式渲染器 |
| `tui_gateway/server.py:9848` 的 `rendered = render_message(raw, cols)` | `message.complete` 的正文渲染 |
| `tui_gateway/methods_tools.py:1335` 的 `rendered = render_diff(raw, session.get("cols", 80))` | diff 渲染 |

### 5.10 `tui_gateway/server.py` —— 14,006 行的骨架

**顶层结构统计**(AST,不 import):

```verify
cd /home/user/hermes-agent && python3 -c "
import ast
t=ast.parse(open('tui_gateway/server.py').read())
k=lambda *T:[n for n in t.body if isinstance(n,T)]
print('classes',len(k(ast.ClassDef)),'funcs',len(k(ast.FunctionDef,ast.AsyncFunctionDef)),
      'assigns',len(k(ast.Assign,ast.AnnAssign)),'imports',len(k(ast.Import,ast.ImportFrom)))
"
# → classes 5  funcs 387  assigns 125  imports 32
```

**5 个顶层类**——注意:14,006 行里只有 5 个类,其中 3 个是异常/标记类。
这个模块**基本不是面向对象的**,它是「一大堆函数 + 一大堆模块级可变状态」。

| 类 | 锚点 + 摘录 | 作用 |
|---|---|---|
| `_DropTransport` | `tui_gateway/server.py:305` 的 `class _DropTransport:` | 断连后的丢弃 sink:`write` 恒 `False`,让会话保持可 resume 而不写出过期帧 |
| `_SlashWorker` | `tui_gateway/server.py:326` 的 `class _SlashWorker:` | 常驻的 HermesCLI 子进程,专跑 slash 命令;两条守护线程分别抽 stdout/stderr |
| `CompressionLockHeld` | `tui_gateway/server.py:4614` 的 `class CompressionLockHeld(Exception):` | 压缩锁被占的信号异常 |
| `_RuntimeFallbackResolution` | `tui_gateway/server.py:6231` 的 `class _RuntimeFallbackResolution(NamedTuple):` | 运行时回落解析结果的具名元组 |
| `_NoProject` | `tui_gateway/server.py:11187` 的 `class _NoProject(Exception):` | projects handler 里 `params['id']` 解析为空的信号异常 |

**分区地图**(27 条 `# ── ` 横幅,机械提取):

```verify
cd /home/user/hermes-agent && grep -c '^# ── ' tui_gateway/server.py   # → 27
cd /home/user/hermes-agent && grep -n '^# ── ' tui_gateway/server.py
```

| 行 | 横幅 | 行 | 横幅 |
|---|---|---|---|
| 62 | Panic logger | 10459 | Methods: respond |
| 184 | Async RPC dispatch (#12546) | 10476 | Methods: config |
| 1298 | Plumbing | 11655 | Methods: tools & system |
| 1381 | per-session profile scoping (global remote mode) | 11900 | Methods: paste |
| 2879 | Config I/O | 11905 | Methods: complete |
| 3103 | Blocking prompt factory | 12232 | Methods: slash.exec |
| 3180 | Agent factory | 12633 | Methods: voice |
| 5524 | Child-session live mirror | 12692 | Streaming TTS (one active pipeline per process) |
| 7169 | Auto-continue: resume a turn killed by a death | 12771 | Full-duplex agent-turn listener (one mic) |
| 7644 | Methods: session | 13003 | Wake word ("Hey Hermes") |
| 8595 | Delegation: subagent tree observability + controls | 13717 | Methods: insights |
| 8601 | Spawn-tree snapshots: TUI-written, disk-persisted | 13720 | Methods: rollback |
| 8663 | Methods: prompt | 13723 | Methods: browser / plugins / cron / skills |
| | | 13987 | Split @method handler modules |

**这些横幅不能当权威地图用**(见 §6 ◇-9):`Methods: session` 横幅在 :7644,
但 62 个 session 方法的实现体已经搬到 `tui_gateway/methods_session.py` 去了;
更要紧的是**协议核心全部落在错误的横幅辖区下**。

**并发模型:一个池 + 十余种后台线程。**

| 设施 | 锚点 + 摘录 | 数量 / 命名 | 生命周期 |
|---|---|---|---|
| RPC 线程池 | `tui_gateway/server.py:292` 的 `_pool = concurrent.futures.ThreadPoolExecutor(` | 默认 8(`HERMES_TUI_RPC_POOL_WORKERS`,下限 `max(2, …)`),前缀 `tui-rpc` | `tui_gateway/server.py:296` 的 `atexit.register(lambda: _pool.shutdown(wait=False, cancel_futures=True))` |
| 空闲回收器 | `tui_gateway/server.py:1285` 的 `def _start_idle_reaper() -> None:` | 1,每 300s 扫一次 | 进程级,守护 |
| 变更监视器 | `tui_gateway/server.py:3452` 的 `name="hermes-change-watcher",` | 1,0.5s tick | `_ensure_skin_watcher` 幂等启动 |
| agent 构建 | `tui_gateway/server.py:2267` 的 `target=_build,` | 每会话 1(延迟构建) | 构建完即退 |
| turn 执行 | `tui_gateway/methods_prompt.py:327` 的 `run_thread = threading.Thread(target=run_after_agent_ready, daemon=True)` | 每 turn 1 | turn 结束即退 |
| git 元数据探测 | `tui_gateway/server.py:2844` 的 `name="git-meta",` | 每次探测 1 | 一次性 |
| MCP 迟到刷新 | `tui_gateway/server.py:6224` 的 `name=f"tui-mcp-late-refresh-{sid}",` | 每会话最多 1 | 一次性 |
| 忙时打断 | `tui_gateway/server.py:7392` 的 `name=f"busy-interrupt-{sid}",` | 每次排队提交 1 | 一次性 |
| 通知轮询 | `tui_gateway/server.py:9343` 的 `target=_notification_poller_loop,` | 每会话 1 | 会话级 |
| 语音全双工 | `tui_gateway/server.py:12793` 的 `name="voice-full-duplex",` | 进程级 1(一只麦克风) | turn 期间 |
| 唤醒词重试 | `tui_gateway/server.py:13094` 的 `name="wake-resume-retry",` | 1 | 一次性 |
| TTS 播放 | `tui_gateway/server.py:12719` 的 `target=stream_tts_to_speaker,` | 进程级 1 条流水线(一只扬声器) | 逐句 |
| slash worker 抽流 | `tui_gateway/server.py:389` 的 `threading.Thread(target=self._drain_stdout, daemon=True).start()` | 每 worker 2 | worker 级 |
| WS 孤儿回收定时器 | `tui_gateway/server.py:1063` 的 `timer = threading.Timer(_WS_ORPHAN_REAP_GRACE_S, _reap)` | 按需 | 一次性,daemon |
| LRU 扫描定时器 | `tui_gateway/server.py:1277` 的 `timer = threading.Timer(0.1, _run)` | 按需 | 一次性,daemon |
| 延迟 agent 构建定时器 | `tui_gateway/server.py:7753` 的 `timer = threading.Timer(delay, _run)` | 按需 | 一次性,daemon |
| 硬退出兜底定时器 | `tui_gateway/entry.py:145` 的 `timer = _threading.Timer(_shutdown_grace_seconds(), _hard_exit)` | 收到信号时 1 | 一次性,daemon |

**共享状态与锁**:

| 锁 | 锚点 + 摘录 | 保护什么 |
|---|---|---|
| `_sessions_lock` | `tui_gateway/server.py:152` 的 `_sessions_lock = threading.RLock()  # reentrant: _close_session_by_id may run under callers that already hold it` | 会话注册表;**可重入**,理由写在同行注释里 |
| `_stdout_lock` | `tui_gateway/server.py:150` 的 `_stdout_lock = threading.Lock()` | stdio 写出 |
| `_cfg_lock` | `tui_gateway/server.py:151` 的 `_cfg_lock = threading.Lock()` | 配置缓存 |
| `_prompt_lock` | `tui_gateway/server.py:153` 的 `_prompt_lock = threading.Lock()` | 阻塞式提问的 `_pending`/`_answers` |
| `_live_transports_lock` | `tui_gateway/server.py:1548` 的 `_live_transports_lock = threading.Lock()` | 全局广播名册 |
| 每会话 `history_lock` | `tui_gateway/server.py:9614` 的 `def _stream(delta):` 里的 `with session["history_lock"]:` | 该会话的历史与在飞增量 |

**stdout 的所有权转移**——这一条是整个协议能稳的前提。
`tui_gateway/server.py:298 @ 863e313`

```
# Reserve real stdout for JSON-RPC only; redirect Python's stdout to stderr
# so stray print() from libraries/tools becomes harmless gateway.stderr instead
# of corrupting the JSON protocol.
_real_stdout = sys.stdout
sys.stdout = sys.stderr
```

**会话生命周期的四道回收**:

| 道 | 锚点 + 摘录 | 触发 / 条件 |
|---|---|---|
| 1 · WS 断连 | `tui_gateway/server.py:1068` 的 `def _close_sessions_for_transport(` | 标记 `close_on_disconnect` 的立即回收,其余转丢弃 sink 并排宽限回收;返回 `(reaped, detached)` 供断连观测 |
| 2 · 孤儿宽限回收 | `tui_gateway/server.py:1027` 的 `def _schedule_ws_orphan_reap(sid: str) -> None:` | 默认 20s(`HERMES_TUI_WS_ORPHAN_REAP_GRACE_S`);快速重连 / `session.resume` 重绑活 transport 会取消它 |
| 3 · TTL 空闲回收 | `tui_gateway/server.py:1137` 的 `def _session_is_evictable(sid: str, session: dict, now: float) -> bool:` + `tui_gateway/server.py:1154` 的 `def _reap_idle_sessions() -> None:` | 默认 6 小时(`HERMES_TUI_SESSION_TTL_S`),每 300s 扫一次 |
| 4 · LRU 软上限 | `tui_gateway/server.py:1226` 的 `def _session_is_lru_evictable(sid: str, session: dict) -> bool:` + `tui_gateway/server.py:1241` 的 `def _enforce_session_cap() -> None:` | 同样的硬豁免但**去掉小时级年龄闸**:一个失去客户端的会话立刻具备被淘汰资格;`max_live_sessions` 为 0/null 则关闭 |

四道共享同一组**硬豁免**:`running` / 有待答提问 / 有活跃委派 / 正在构建(非 lazy)/ transport 还活着。
`tui_gateway/server.py:1137 @ 863e313`

```
def _session_is_evictable(sid: str, session: dict, now: float) -> bool:
    if session.get("running") or _session_pending_kind(sid):
        return False
    if _session_has_active_delegations(sid, session):
        return False
    ready = session.get("agent_ready")
    # Lazy watch sessions (subagent spectator windows) never start a build,
    # so their forever-unset agent_ready must not make them immortal.
    if ready is not None and not ready.is_set() and not session.get("lazy"):
        return False
    if not _transport_is_dead(session.get("transport")):
        return False
    last_active = float(session.get("last_active") or 0.0)
    created_at = float(session.get("created_at") or 0.0)
    return (now - last_active) > _SESSION_TTL_S and (now - created_at) > _SESSION_TTL_S
```

`_transport_is_dead` 的判定里有一条容易踩的细节,`tui_gateway/server.py:1127 @ 863e313`

```
def _transport_is_dead(transport) -> bool:
    # _detached_ws_transport is the post-WS-disconnect drop sentinel; a session
    # parked on it has no live client. _stdio_transport is the REAL transport
    # for a standalone `hermes --tui`, so it must NOT count as dead here (doing
    # so let the idle reaper evict healthy standalone TUI sessions).
    if transport is _detached_ws_transport:
        return True
    return getattr(transport, "_closed", None) is True
```

**进程退出**:`tui_gateway/server.py:1294` 的 `atexit.register(_shutdown_sessions)` 注册,
`tui_gateway/server.py:1105` 的 `def _shutdown_sessions() -> None:` 先释放唤醒词归属,
再逐个 `_close_session_by_id(end_reason="tui_shutdown")`。
`tui_gateway/entry.py:158` 的 `_shutdown_sessions()` 在信号处理器里**显式再调一次**,
因为持有 GIL / `_stdout_lock` 的 worker 线程可能让 atexit 在宽限窗口内跑不完。

---

## §6 发现清单

### ■-1 `tui_gateway/render.py` 整个模块在本基线上永久失效:`agent/rich_output.py` 不存在

模块 docstring 声称当 `agent.rich_output` 存在时用它。`tui_gateway/render.py:1 @ 863e313`

```
"""Rendering bridge — routes TUI content through Python-side renderers.

When agent.rich_output exists, its functions are used. When it doesn't,
everything returns None and the TUI falls back to its own markdown.tsx.
"""
```

本基线上它**不存在**,于是 `render_message` / `render_diff` / `make_stream_renderer`
三个函数**恒返回 `None`**,§5.9 那四个调用点全部走 TUI 自带 `markdown.tsx` 的回落路径。
即「Python 侧渲染」这个特性在本 commit 上**不可达**。

**负结论的搜索面**(三层,逐层都为空):

```verify
cd /home/user/hermes-agent
# 1) 文件名/包目录层:任何叫 rich_output 的文件或目录
find . -name 'rich_output*' -not -path '*/node_modules/*' -not -path '*/.git/*'
# → 无输出

# 2) Python 源码层:所有 *.py 里的 rich_output 字面量
grep -rn 'rich_output' --include=*.py . | grep -v __pycache__
# → 6 处,全部是引用方:render.py 的 3 个 import + 1 行 docstring
#   + tests/tui_gateway/test_render.py 的 2 处 monkeypatch。零个定义处。

# 3) 全文件类型层(排除 node_modules / .git / __pycache__):谁提到过这个名字
grep -rl 'rich_output' . --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=__pycache__
# → 只有 ./tui_gateway/render.py 与 ./tests/tui_gateway/test_render.py
```

第 3 层排除了「由插件 / lazy-install / 打包脚本在运行时生成」的可能:
若有任何构建产物、`pyproject.toml` entry point、插件清单提到它,这一层会命中。

**唯一的测试也只测回落分支**:`tests/tui_gateway/test_render.py:20` 的
`with _no_rich():` 与 `tests/tui_gateway/test_render.py:27` 的 `with _no_rich():`
是两个用例的全部,而它专门写了个助手
`tests/tui_gateway/test_render.py:8` 的 `def _stub_rich(mock_mod):` **从未被调用**——
也就是说「模块存在时」那半边行为**从来没被任何测试执行过**。

**判定为 ■ 而非 ◇ 的理由**:这不是「代码有、文档无」,而是「文档承诺了一条代码永远走不到的路」,
外加 49 行不可达代码 + 一个只覆盖一半的测试。
**另一种可能的解读**(诚实标注):这是一条为下游/闭源模块留的**可选依赖接缝**,
"exists / doesn't" 的措辞本身就承认两种状态。但第 3 层搜索表明本仓库里没有任何东西会提供它,
所以在本基线的语境下它是死的。

### ▲-2 `tui_gateway/ws.py:38` 的注释与它下方 130 行处的代码矛盾

`tui_gateway/ws.py:38 @ 863e313`

```
# Max seconds a pool-dispatched handler will block waiting for the event loop
# to flush a WS frame before we mark the transport dead. Protects handler
# threads from a wedged socket.
_WS_WRITE_TIMEOUT_S = 10.0
```

注释说超时"before we mark the transport dead"。代码**明确不这么做**:
§5.3 已逐字引用的 `tui_gateway/ws.py:165` 那段 `TimeoutError` 分支只打一行 warning
并 `return not self._closed`,**不置 `_closed`**,而且分支里的注释还专门解释了为什么改的
(「latching `_closed` here permanently silenced live windows after one slow write」)。
即修 bug 时改了实现、没回头改模块顶部那三行注释。
**整段判定**:三句话里,第一句(超时后标记 transport 已死)为假,
第二句 "Protects handler threads from a wedged socket" 为真(超时确实放开了 worker 线程)。
一句假,故为 ▲。

### ▲-3 `tui_gateway/ws.py:8` 的 "Wire protocol" 段落:三句里两句为假

`tui_gateway/ws.py:8 @ 863e313`

```
Wire protocol
-------------
Identical to stdio: newline-delimited JSON-RPC in both directions. The server
emits a ``gateway.ready`` event immediately after connection accept, then
echoes responses/events for inbound requests. No framing differences.
```

按「整段判定 + 确认归哪个标题管」:这段归 `Wire protocol` 标题管,做了三个断言。

1. **"newline-delimited JSON-RPC in both directions" —— 假,两个方向都假。**
   出站:§3.3 逐字引用的 `tui_gateway/ws.py:118` 与 `tui_gateway/ws.py:220`
   的 `json.dumps(obj, ensure_ascii=False)` 都**不加 `\n`**;而 stdio 的
   `tui_gateway/transport.py:137` 加了。
   入站:§3.3 逐字引用的 `tui_gateway/ws.py:354` 是「一条 WS message → `strip()` →
   一次 `json.loads`」,不做换行切分,所以一条 message 里放两个换行分隔的 JSON 会直接 parse error。
2. **"emits a `gateway.ready` event immediately after connection accept" —— 真**
   (`tui_gateway/ws.py:297` accept,`tui_gateway/ws.py:314` 发 ready;
   中间只插了 `_disable_nagle` 与放到线程池的 `resolve_skin`)。
3. **"No framing differences." —— 假。** 帧边界在 stdio 上是换行符,在 WS 上是 message 边界。
   更具体地,`_safe_send_many` 把一批 N 帧发成 **N 条独立 message**:
   `tui_gateway/ws.py:233 @ 863e313`

```
            try:
                for line in lines:
                    if self._closed:
                        return
                    await self._ws.send_text(line)
```

**客户端自己就是反证**:§3.3 那张表列了同一个 `gatewayClient.ts` 里 stdio 与 WS
两套读写规矩——stdio 用行读器并补 `'\n'`,WS 用整条 message 且不补。

*为什么这不只是抠字眼*:这段 docstring 的读者是「想把 `handle_ws` 挂进自己 FastAPI app 的人」
(紧接着的 `Mounting` 段就是给他们的)。照这段话去写客户端——累积字节、按 `\n` 切——
在单帧场景下会碰巧能跑,在合批的 token 流下就会看到「一条 message 一个 JSON、没有分隔符」,
而 bug 出现的时机是回复正在高速流的时候。

### ▲-4 `tui_gateway/event_publisher.py:10` 的 "Wire protocol" 一句:两个断言都假

`tui_gateway/event_publisher.py:10 @ 863e313`

```
Wire protocol: newline-framed JSON dicts (the same shape the dispatcher
already passes to ``write``).  No JSON-RPC envelope here — the dashboard's
``/api/pub`` endpoint just rebroadcasts the bytes verbatim to subscribers.
```

1. **"newline-framed" —— 假**:§3.3 逐字引用的 `tui_gateway/event_publisher.py:90`
   里 `line = json.dumps(obj, ensure_ascii=False)` 不加换行,
   而接收端 `hermes_cli/web_server.py:15897` 的
   `await _broadcast_event(ws.app, channel, await ws.receive_text())` 也是按 message 收的。
2. **"No JSON-RPC envelope here" —— 假**:`TeeTransport` 把 dispatcher 的 `obj` 原样传下来,
   那就是完整的 JSON-RPC 事件帧;最终消费者 `web/src/components/ChatSidebar.tsx:356` 的
   `if (frame.method !== "event" || !frame.params) {` 表明它**依赖**这个信封存在。
   *宽容解读*:作者想说的可能是「本模块不再额外包一层」。但字面表述会让读者以为拿到的是裸 payload,
   而实际必须先读 `frame.params.type` 才拿得到事件类型。
3. 第三个分句 "rebroadcasts the bytes verbatim" 为**真**。

### ▲-5 `AGENTS.md:445` 让读者去 `tui_gateway/server.py` 找 "the full method/event catalog"

原文在 `## TUI Architecture (ui-tui + tui_gateway)` → `### Transport` 标题下,`AGENTS.md:445 @ 863e313`

> Newline-delimited JSON-RPC over stdio. Requests from Ink, events from Python. See `tui_gateway/server.py` for the full method/event catalog.

**整段判定**:
第一句 "Newline-delimited JSON-RPC over stdio" 在这个标题下**为真**——该节的 Process Model 图
(`AGENTS.md:436` 画的是 `└─ Node (Ink) ──stdio JSON-RPC── Python (tui_gateway)`)辖域是 stdio,
而 stdio 确实按换行分帧(§3.3)。**这一句不是 ▲。**
第二句 "Requests from Ink, events from Python" 为真。
**第三句为假**:`tui_gateway/server.py` 只注册 **21 / 144** 条方法(14.6%);
其余 123 条在 `tui_gateway/methods_session.py`(62)、`methods_tools.py`(32)、
`methods_prompt.py`(16)、`methods_config.py`(7)、`methods_complete.py`(6)。
事件侧同样分裂(§3.2 末)。而且 server.py 里**根本没有一张 "catalog"**——`_methods` 是
六个文件在导入期共同填出来的字典,没有任何清单形态的东西可读。
按 AGENTS.md 的指引去 server.py 找方法表,会漏掉 85% 的方法。

### ◇-6 `tui_gateway/loop_noise.py` 的唯一生产安装点在包外,`tui_gateway/ws.py` 自己从不安装它

模块 docstring 第一句说它治的是 "the gateway serving loop"
(`tui_gateway/loop_noise.py:1` 的 `"""Suppress benign event-loop teardown noise on the gateway serving loop.`)。但:

```verify
cd /home/user/hermes-agent && grep -rn 'install_loop_noise_filter' --include=*.py . | grep -v __pycache__
# → 4 处:定义 1(tui_gateway/loop_noise.py:54)、测试 2(tests/test_tui_gateway_loop_noise.py)、
#   生产调用 1(hermes_cli/web_server.py:17654)
```

唯一的生产安装点是 `hermes_cli/web_server.py:17654` 的
`install_loop_noise_filter(asyncio.get_running_loop())`,发生在 uvicorn 起来之后。
`tui_gateway/ws.py` 里**没有任何一处**调它。在当前部署形态下这是自洽的——
`handle_ws` 就跑在那个 loop 上。但 `tui_gateway/ws.py:19` 的
`@app.websocket("/api/ws")` 那段 `Mounting` 示例教读者把 `handle_ws` 挂到**自己的**
FastAPI app 上,而照做的人拿不到这层过滤:桌面客户端硬断一次,
他的日志里就会出现 docstring 里描述的那 50+ 份 traceback。文档没有一处提到这个依赖关系,故记 ◇。

### ◇-7 sidecar 发布器的连接是**同步的**,且落在 `gateway.ready` 之前的启动关键路径上

`tui_gateway/entry.py:431` 的 `_install_sidecar_publisher()` 在 `tui_gateway/entry.py:443` 的
`if not write_json({` 之前执行;它构造 `WsPublisherTransport(url)`,而构造函数里
`tui_gateway/event_publisher.py:57` 的
`self._ws = ws_connect(url, open_timeout=connect_timeout, max_size=None)`
是一次**阻塞的**同步连接,`connect_timeout` 默认 2.0s
(`tui_gateway/event_publisher.py:43` 的 `def __init__(self, url: str, *, connect_timeout: float = 2.0) -> None:`)。
即:设了 `HERMES_TUI_SIDECAR_URL` 而对端不可达时,TUI 的首帧会被推迟最多 2 秒。
模块 docstring 只讲了 "Failure mode: silent" 与「不阻塞 agent 循环」,没讲它会阻塞**启动**;
`tui_gateway/entry.py:53` 的 `Best-effort: connect failure or runtime drop falls back to stdio-only.`
同样只说结果不说代价。故记 ◇。

### ◎-8 `tui_gateway/server.py:185` 说 "A handful of handlers",实为 42 条

`tui_gateway/server.py:184 @ 863e313`

```
# ── Async RPC dispatch (#12546) ──────────────────────────────────────
# A handful of handlers block the dispatcher loop in entry.py for seconds
# to minutes (slash.exec, cli.exec, shell.exec, session.resume,
# session.branch, session.compress, skills.manage).  While they're running, inbound RPCs —
# notably approval.respond and session.interrupt — sit unread in the
# stdin pipe.  We route only those slow handlers onto a small thread pool;
# everything else stays on the main thread so ordering stays sane for the
# fast path.  write_json is already _stdout_lock-guarded, so concurrent
# response writes are safe.
_LONG_HANDLERS = frozenset(
```

括号里点名 7 条,而紧接着的 `_LONG_HANDLERS` 现有 **42 条**(§3.4)。
"a handful"、"only those slow handlers"、"a small thread pool" 在 7 条时成立,
在 42 条 + 8 worker 时**显著保守**——但字面并非虚假(42 条确实都是慢 handler,池确实不大),
且集合本身就在下一行,不构成误导性冲突。故记 ◎ 而非 ▲。
*(实际的读者风险在别处:括号里那 7 条会被当成完整清单来记忆。)*

### ◇-9 `tui_gateway/server.py` 的横幅分区与内容错位,协议核心全在错误的辖区下

`tui_gateway/server.py:1381` 的 `# ── per-session profile scoping (global remote mode) ───────────────────────────`
这条横幅的下一条横幅在 `tui_gateway/server.py:2879` 的
`# ── Config I/O ────────────────────────────────────────────────────────`,
所以它名义上的辖区是 :1381–:2878。而这个区间里装着整个协议核心:

| 落在错误辖区里的东西 | 锚点 + 摘录 |
|---|---|
| 事件帧构造 | `tui_gateway/server.py:1534` 的 `def _event_frame(event: str, sid: str, payload: dict | None = None) -> dict:` |
| 帧路由阶梯 | `tui_gateway/server.py:1511` 的 `def write_json(obj: dict) -> bool:` |
| 事件发射 | `tui_gateway/server.py:1539` 的 `def _emit(event: str, sid: str, payload: dict | None = None):` |
| 全局广播 | `tui_gateway/server.py:1565` 的 `def _broadcast_global_event(event: str, payload: dict | None = None) -> None:` |
| 响应信封 | `tui_gateway/server.py:1856` 的 `def _ok(rid, result: dict) -> dict:` 与 `tui_gateway/server.py:1860` 的 `def _err(rid, code: int, msg: str) -> dict:` |
| 方法注册 | `tui_gateway/server.py:1864` 的 `def method(name: str):` |
| 请求校验 | `tui_gateway/server.py:1872` 的 `def _normalize_request(req: Any) -> tuple[Any, str, dict] | dict:` |
| 查表分发 | `tui_gateway/server.py:1891` 的 `def handle_request(req: dict) -> dict | None:` |
| 并发路由 | `tui_gateway/server.py:1903` 的 `def dispatch(req: dict, transport: Optional[Transport] = None) -> dict | None:` |

而名字最像协议核心的那条横幅 `tui_gateway/server.py:1298` 的
`# ── Plumbing ──────────────────────────────────────────────────────────`
辖区只有 :1298–:1380,里面**没有**上面任何一项。
这不是代码缺陷,而是「作者自绘的内部地图与内容脱节」——文档(此处即横幅注释)没有声明
它其实不是分区边界,故记 ◇。后续任何要在 server.py 里定位的人,应把 §5.10 的横幅表
**当行号索引用,不要当语义分区用**。

---

## §7 未取证与推定

明确列出本片**没有验**的东西:

1. **没有真跑过 gateway**。全片结论来自静态阅读 + AST 枚举 + 一次
   `import tui_gateway.server` 取 `_methods` 长度。没有起过 `hermes --tui`、
   没有连过 WebSocket、没有观察过任何真实帧。所以「64 种事件在真实会话里都会出现」
   这句话**我没有验**——我验的是「代码里存在这 64 条发射路径」。
   有些路径需要特定配置才可达(如 `pet.*` 需要 petdex、`wake.*` 需要唤醒词依赖、
   `billing.step_up.verification` 需要 portal 凭据)。
2. **没有跑本片相关的测试**。`tests/tui_gateway/test_protocol.py`(27 个用例)、
   `tests/test_tui_gateway_ws.py`(6 个)、`tests/test_tui_gateway_loop_noise.py`、
   `tests/tui_gateway/test_render.py`、`tests/tui_gateway/test_inline_rpc_gil_starvation.py`
   都只是**读**了,用作行为规格参照,未执行(派工书禁止装包,共享 venv 的报数由主线负责)。
3. **`tui_gateway/server.py` 的实现体基本没读**。按 L2 判据这是有意的:387 个顶层函数里,
   我逐字读了协议骨架相关的约 25 个(`write_json`、`_emit`、`_event_frame`、
   `_broadcast_global_event`、`dispatch`、`handle_request`、`_normalize_request`、`_ok`、`_err`、
   `method`、`_block`、`_broadcast_watched_changes`、`_on_tool_start`、`_on_tool_progress`、
   `_mirror_subagent_to_child`、`_close_sessions_for_transport`、`_shutdown_sessions`、
   `_transport_is_dead`、`_session_is_evictable`、`_reap_idle_sessions`、`_enforce_session_cap`、
   `_start_idle_reaper`、`_retire_turn_marker`、`_maybe_schedule_auto_continue`、
   `_run_prompt_submit` 的头部)。其余约 360 个只从签名 / 横幅 / 调用关系上定位,**没读实现**。
4. **`_on_tool_progress` 的 `event_type` 白名单我是逆推的**,不是从一个声明式表格读出来的:
   函数体是一串 `if event_type == "…"` 早返回 + 一个 `startswith("subagent.")` 兜底。
   `subagent.*` 的具体取值是从**发射侧**(`tools/delegate_tool.py`、`tools/delegation_live_log.py`)
   grep 出来的 7 种,减去 `subagent.text` 得 6 种。
   **推定**:如果将来有第三个模块发出新的 `subagent.X`,它会自动出现在线上而这张表不会更新。
5. **`desktop_ui` 那 3 种事件**(`pane.reveal`/`preview.open`/`message.reaction`)是从
   `tools/*.py` 的 `desktop_ui.emit(...)` 调用点枚举的。搜索面是
   `grep -rn 'desktop_ui.emit(' --include=*.py .`,命中 5 处(含 2 处测试)。
   **未排除**:`emit` 的第一参数如果哪里是变量而非字面量,这个枚举会漏。我没做 AST 校验。
6. **`tui_gateway/ws.py` 的两把锁我没有做形式化的顺序论证**。我读了注释声明的不变量
   (「在线序 == 缓冲序」)并确认存在覆盖它的测试
   (`tests/test_tui_gateway_ws.py:193` 的 `def test_ws_transport_preserves_cross_batch_order():`),
   但没有独立推导 `asyncio.Lock` 的 FIFO 性质在所有调度交错下都成立,也没跑那个测试。
7. **`_arm_token_flush` 的一个竞态我看见了但没定性**:它在 loop 线程上无锁写
   `self._token_flush_handle`,而 `write` 在 `_token_lock` 内 `call_soon_threadsafe` 排它。
   我推演出一条能让两个定时器同时在飞、并让一个 `TimerHandle` 泄漏(close 时取消不到)的交错,
   但**没有构造复现**,而且其后果(多一次空 flush + 一个不再触发任何行为的定时器)看起来无害。
   故**不**记为 ■,列在此处待后续证实或否证。
8. **`tui_gateway/server.py` 的 30 个环境变量**只列了名字,没逐个查语义与默认值。
   它们大半服务 handler,归别的片。
9. **横幅地图的错位我只核了一条**(◇-9,`per-session profile scoping` 那条)。
   其余 26 条横幅与其辖区内容是否吻合,**没有逐条核**。所以 §5.10 那张表要当行号索引用。
10. **`method_ctx` 的 `install` 我没有验证 `__closure__` 传递在有真实闭包的 handler 上的行为**。
    `types.FunctionType(code, g, name, defaults, closure)` 保留了原闭包单元;
    如果某个 `methods_*` handler 闭包引用了它**自己模块**的局部(而非模块全局),
    那个引用会继续指向原模块——这是正确的,但我没有找一个实例证实。
11. **`_stdin_recovery` 的故障我没有复现**。恢复逻辑的正确性我是从 POSIX 语义
    (文件状态标志挂在 open file description 上)+ 代码 + docstring 三者一致推断的,
    没有写一个翻 `O_NONBLOCK` 的子进程去实测。
12. **`_LONG_HANDLERS` 的下限我没有当成 ■ 报**:`tui_gateway/server.py:287` 的
    `2, int(os.environ.get("HERMES_TUI_RPC_POOL_WORKERS") or "8")` 允许把池压到 2,
    而 `tests/tui_gateway/test_inline_rpc_gil_starvation.py:139` 的
    `assert server._rpc_pool_workers >= 8, (` 断言的是**默认值** ≥ 8。
    环境变量覆盖是刻意的逃生舱,不是缺陷;但「设成 2 会让那条不变量失效」这件事没被任何东西挡住。

---

## §8 L2 判据自评

**判据 1 · 点名到位 —— 达成。**
片内 11 个文件全部在 §2 表格里以**全路径**出现并各有一句话角色,
且 11 个中有 10 个在 §5 有自己的小节(唯一例外是 `tui_gateway/__init__.py`,
它 0 字节、0 行,无可读之物,已在 §2 交代其角色与「不做 re-export」这一事实)。
**全文引用零裸文件名**——修订时把初稿里约 60 处 `ws.py:38`、`server.py:1068` 这类
裸名全部改成从仓库根可解析的全路径。

**判据 2 · 接缝穷举 —— 达成,5 个接缝全列不抽样。**

| 接缝 | 条数 | 是否全列 | 机械枚举命令 |
|---|---|---|---|
| JSON-RPC 方法表 | 144 | 是(§3.1 按拥有者文件分 6 组全列) | grep + 运行时 `len(server._methods)` 双路交叉验证,两边都 144 |
| 协议层错误码 | 6 | 是(§3.1 末表,逐个带产生处) | 手工穷举 6 个 `_err` / 字面量构造点 |
| 对外事件类型表 | 64 | 是(§3.2 按语义分 15 组全列) | AST 枚举 39 字面量 + 9 处动态点逐个定死 + 「事件帧构造点全仓只有 4 处」这一完备性论证 |
| 传输帧格式 | 3 条通道 | 是(§3.3 出站/入站/边界三列全填) | 各通道的 `json.dumps` 行逐字引用 |
| 池路由集合 `_LONG_HANDLERS` | 42 | 是(§3.4 全列) | AST 取集合字面量;并与 144 条方法名 `comm -23` 核对无失效项 |

另补一个非派工要求的小接缝:本片环境变量 3 条(§3.5,附「其余 6 个文件零环境变量」的枚举命令)。

**判据 3 · 一条端到端链走通 —— 达成。**
§4 给了「用户按 Enter → 屏幕第一个 token」的 20 跳链,**每一跳带锚点**,
两端都超出本片并已写清接到谁:上游接 `ui-tui/src/gatewayClient.ts`(Ink 客户端),
下游接 `tui_gateway/methods_prompt.py` → `server._run_prompt_submit` → `AIAgent.run_conversation`。
链上跨片的三跳我读了原文并逐字引了其中最关键的一处(transport 重绑),但没展开其实现。
另用一张表把 WS 形态同一条链的 5 处差异标了出来。

**判据 4 · 两处以上逐字取证 —— 达成,共 31 个逐字源码块。**
分布:`tui_gateway/transport.py` 4、`tui_gateway/ws.py` 7、`tui_gateway/event_publisher.py` 2、
`tui_gateway/entry.py` 2、`tui_gateway/server.py` 12、`tui_gateway/method_ctx.py` 2、
`tui_gateway/_stdin_recovery.py` 2、`tui_gateway/loop_noise.py` 2、`tui_gateway/turn_marker.py` 1、
`tui_gateway/render.py` 2、`tui_gateway/methods_prompt.py` 1。
全部用 `sed -n 'A,Bp'` 取出后粘贴,未手抄。
另有约 90 处表格行内锚点采用「锚点 + 紧跟反引号摘录」的声明式写法,同样被脚本机械比对。

**判据 5 · 至少一条记号 —— 达成,共 9 条**:■ 1 条、▲ 4 条、◇ 3 条、◎ 1 条,逐条带锚点。
其中 ■-1 与 ▲-3/▲-4 都给出了完整搜索面或客户端侧反证,不是「我没看见」。

**没做到 / 打折的部分(如实列)**:

- **判据 2 的「事件类型」一栏有一个诚实的边界**:我穷举的是**发射路径**,不是
  「真实会话里可观测到的事件」。两者的差在于配置门控(见 §7 第 1 条)。
- **`tui_gateway/turn_marker.py` 只有 1 个逐字围栏块**(它的问题陈述),
  其三个函数与全部设计点是用表格行内声明式锚点给的。这满足校验器,但取证密度低于其它文件。
- **§5.10 的横幅表只核了一条错位**(◇-9);其余 26 条没逐条核(§7 第 9 条)。
- **§7 第 7 条那个竞态没定性**——看见了、推演了、没复现,所以没敢记 ■。
- 完全没有执行任何测试或运行任何 gateway 形态(§7 第 1、2 条)。

---

## §9 移交

| 编号 | 锚点 + 摘录 | 一句话现象 | 建议接手 |
|---|---|---|---|
| H-R10A-a | `tui_gateway/render.py:12` 的 `from agent.rich_output import format_response` | `agent/rich_output.py` 在基线里不存在(三层搜索面见 §6 ■-1),故三个渲染函数恒返回 `None`,四个调用点全走 TUI 自带渲染;需判定这是废弃残留还是给下游模块留的可选接缝。 | agent 片(它拥有 `agent/` 目录,能确认该模块是否曾存在、何时删的) |
| H-R10A-b | `tui_gateway/ws.py:38` 的 `# Max seconds a pool-dispatched handler will block waiting for the event loop` | 这行注释说超时后 "mark the transport dead",而 130 行之后的 `TimeoutError` 分支明确不置 `_closed`;修 bug 时改了实现没回改注释。 | R10 主线(登记为 ▲,归入本轮 ▲ 计数) |
| H-R10A-c | `tui_gateway/server.py:1381` 的 `# ── per-session profile scoping (global remote mode) ───────────────────────────` | 这条横幅的辖区(:1381–:2878)里装着整个协议核心:`write_json`(:1511)、`_emit`(:1539)、`_ok`/`_err`/`method`(:1856–:1870)、`handle_request`(:1891)、`dispatch`(:1903);拿横幅当分区地图会找错地方。 | 任何后续要在 `tui_gateway/server.py` 里定位的片 |
| H-R10A-d | `tui_gateway/server.py:5518` 的 `if event_type != "subagent.text":` | `subagent.*` 中继是「白名单早返回 + `startswith` 兜底」结构,具体取值只能从发射侧(`tools/delegate_tool.py`)逆推;新增一种 `subagent.X` 会自动上线而无人维护清单。请核这 7 种(减 `subagent.text` 得线上 6 种)是否完整。 | 委派 / 子代理片 |
| H-R10A-e | `tui_gateway/event_publisher.py:57` 的 `self._ws = ws_connect(url, open_timeout=connect_timeout, max_size=None)` | 这是同步阻塞连接、默认 2s 超时,且发生在 `gateway.ready` 之前;设了 `HERMES_TUI_SIDECAR_URL` 而对端不可达时 TUI 首帧被推迟最多 2s,文档只讲 best-effort 不讲启动代价。 | dashboard / web_server 片(它拥有 `/api/pub` 的另一端) |
| H-R10A-f | `hermes_cli/web_server.py:17654` 的 `install_loop_noise_filter(asyncio.get_running_loop())` | `tui_gateway/loop_noise.py` 唯一的生产安装点在包外;`tui_gateway/ws.py` 自己从不安装,照它 `Mounting` 段落自建 FastAPI app 的人拿不到这层过滤。 | dashboard / web_server 片 |
| H-R10A-g | `tui_gateway/ws.py:189` 的 `def _arm_token_flush(self) -> None:` | 它在 loop 线程无锁写 `self._token_flush_handle`,而 `write` 在 `_token_lock` 内排它;推演出一条能让两个定时器同时在飞并泄漏一个 `TimerHandle` 的交错,后果看似无害(多一次空 flush),未构造复现故未记 ■。 | 后续任何做 ws 并发 L1 精读的片 |
| H-R10A-h | `tui_gateway/server.py:287` 的 `2, int(os.environ.get("HERMES_TUI_RPC_POOL_WORKERS") or "8")` | 池下限是 `max(2, …)`,而 `tests/tui_gateway/test_inline_rpc_gil_starvation.py:138` 的 `assert server._rpc_pool_workers >= 8, (` 只断言默认值;把环境变量设成 2 会让那条「前端轮询 RPC 不被饿死」的不变量失效,没有任何机制挡住。 | 配置 / 环境变量片 |
