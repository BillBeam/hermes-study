# r7b-95 · 测试作为行为规格(R7B)

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`。
> 运行方式:`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh <files>`

## 0. 结论

**四批 117 个文件 / 1,102 个用例通过,0 个行为失败;1 个失败经查证为容器无 IPv6 栈的环境限制。**

## 1. 环境重建(本轮新增发现)

R7 报告记录过"一次 venv 缺 aiohttp 为环境问题"。本轮定位了根因并给出确定修法:

`aiohttp` **不在 `[dev]` extra 里**,而在 `messaging` / `slack` / `matrix` / `teams` /
`homeassistant` / `sms` 等平台 extra 里(`pyproject.toml:176 @ 863e313`):

```
messaging = ["python-telegram-bot[webhooks]==22.6", "discord.py[voice]==2.7.1", "aiohttp==3.14.1", ...]
```

而 `gateway/platforms/api_server.py`、`webhook.py`、`whatsapp_cloud.py` 都直接依赖 aiohttp。
所以 CLAUDE.md 的"测试环境"一节对 R7B 这一簇不够用。**修正的重建步骤**:

```bash
python3 -m venv /home/user/hermes-venv
/home/user/hermes-venv/bin/pip install -e "/home/user/hermes-agent[dev]"
/home/user/hermes-venv/bin/pip install "aiohttp==3.14.1" "brotlicffi==1.2.0.1"   # ← R7B 新增
```

装完之后 `tests/gateway/test_api_server*.py` 等 20 个文件从"收集失败"变为全通过。

## 2. 四批运行结果

| 批次 | 文件 | 用例 | 结果 |
|---|---|---|---|
| 1 · relay + platforms 目录 | 30 | 159 | 全通过(8.9s) |
| 2 · api_server + base 契约/守卫 | 20 | 329 | 全通过(8.9s) |
| 3 · 各适配器 + helpers + 媒体 | 40 | 491 | 全通过(10.2s) |
| 4 · 媒体标记/投递/忙时/关停 | 27 | 123 | 全通过(7.0s) |
| **合计** | **117** | **1,102** | **0 行为失败** |

## 3. 唯一一次失败:确证为环境限制

`tests/gateway/test_webhook_adapter.py::TestDualStackBind::test_default_bind_serves_both_families`

```
E           AssertionError: IPv6 bind missing (the 6PN reachability bug) — got [('0.0.0.0', 40755)]
```

判定依据(在本容器内实测):

```
$ python3 -c "import socket; s=socket.socket(socket.AF_INET6, socket.SOCK_STREAM); s.bind(('::',0))"
OSError: [Errno 97] Address family not supported by protocol
$ cat /proc/net/if_inet6
cat: /proc/net/if_inet6: No such file or directory
```

**本容器根本没有 IPv6 协议族**。被测代码 `DEFAULT_HOST = None`
(`gateway/platforms/webhook.py:129 @ 863e313`)的语义正是"让事件循环按**解析出的
每个地址族**各建一个监听套接字" —— 在只解析出 IPv4 的宿主上,只建 IPv4 套接字是
**正确行为**。该用例断言宿主同时具备 v4/v6,属对运行环境的前置要求,不是代码缺陷。

其余 33 个同文件用例全部通过。

## 4. 用 issue 编号命名的规格测试(本簇全部纳入并通过)

| 测试 | 钉住的不变量 | 对应底稿 |
|---|---|---|
| `test_session_split_brain_11016.py` | 属主任务已死时,入口自愈清理陈旧守卫 | `r7b-20` §4 |
| `test_25107_stale_base_url_api_mode.py` | api_mode 下 base_url 不滞留 | `r7b-40` |
| `test_73771_media_resend_dedup.py` | 同一媒体不重复投递 | `r7b-30` |
| `test_75349_whatsapp_multiplex_secret_scope.py` | 多 profile 下 WhatsApp 密钥不串味 | `r7b-50` §5 |
| `test_telegram_prune_stale_topic_binding_31501.py` | 陈旧 topic 绑定被剪枝 | `r7b-10` §3.1 |

## 5. 几个把"设计意图"钉得最死的测试

- **`tests/gateway/relay/test_contract_doc_conformance.py`** —— 把代码与
  `docs/relay-connector-contract.md` 对齐检查。**全仓少见的"文档即测试"**:
  它让 relay 成为本轮文档一致性最好的一簇(见 `r7b-60` §8 说明)。
- **`tests/gateway/relay/test_no_stub_leak.py`** —— 保证测试替身不泄漏进生产路径。
- **`tests/gateway/relay/test_relay_per_platform_caps.py`** —— 钉住"多描述符按平台存表、
  不塌缩成最后写入者胜"(`r7b-60` §4.1)。
- **`tests/gateway/test_base_topic_sessions.py`** / **`test_dm_topics.py`** ——
  topic 恢复后的会话键行为(`r7b-10` §3.1)。
- **`tests/gateway/test_adapter_connect_is_reconnect_contract.py`** ——
  `connect(is_reconnect=...)` 的契约(平台锁 takeover 只在首连武装,`r7b-10` §4.2)。
- **`tests/gateway/test_async_delivery_capability.py`** —— HTTP 通道不可异步投递
  (#10760,`r7b-40` §3)。

## 6. 覆盖口径说明

本轮跑的 117 个文件是**与 R7B 范围直接相关**的规格集(`tests/gateway/relay/**`、
`tests/gateway/platforms/**`,以及 `tests/gateway/` 下按 api_server / base / 各适配器 /
helpers / 媒体 / 忙时守卫筛出的文件)。未跑全量 `tests/`(R7 已做过 Top-42 大盘),
本轮不重复;**未跑的部分不在本轮结论的断言范围内**,如实声明。
