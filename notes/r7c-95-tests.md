# r7c-95 · 测试作为行为规格(R7C)

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`。
> 运行方式:`HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh <files>`

## 0. 结论

**主线四批 137 个文件 / 1,081 个用例通过,0 个行为失败;1 个失败为已知容器限制(无 IPv6)。**

## 1. 环境

按本轮并入 `CLAUDE.md` 的新步骤重建,一次成功:

```bash
python3 -m venv /home/user/hermes-venv
/home/user/hermes-venv/bin/pip install -e "/home/user/hermes-agent[dev]"
/home/user/hermes-venv/bin/pip install "aiohttp==3.14.1" "brotlicffi==1.2.0.1"
```

R7B 遗留的"约 20 个文件收集期 ImportError"未再出现 —— 该修法确认有效,已固化进 `CLAUDE.md`。

## 2. 主线四批

| 批次 | 文件 | 用例 | 结果 |
|---|---:|---:|---|
| 1 · `tests/cron/` 全目录 | 37 | 413 | 全通过(23.6s / 8 workers) |
| 2 · gateway 外围面 1/3 | 33 | 213 | 全通过(11.5s) |
| 3 · gateway 外围面 2/3 | 34 | 255 | 全通过(17.5s) |
| 4 · gateway 外围面 3/3 | 33 | 200 | 1 失败(见 §3) |
| **合计** | **137** | **1,081** | **0 行为失败** |

批次 2–4 的文件集由本簇关键词筛出(`slash|authz|pair|status|deliver|shutdown|drain|restart|
readiness|kanban|hook|scale_to_zero|channel_director|mirror|sticker|dead_target|runtime_footer|
lifecycle|systemd|cgroup|code_skew|whatsapp_identity|response_filter|platform_registry|
display_config|tts|forensic|flush`),共 100 个文件,三等分。

## 3. 唯一失败:已知容器限制,非代码缺陷

```
FAILED tests/gateway/test_webhook_adapter.py::TestDualStackBind::test_default_bind_serves_both_families
```

与 R7B 判定同一条,原因已写进 `CLAUDE.md`:本类云端容器无 IPv6 协议族,而
`DEFAULT_HOST = None`(`gateway/platforms/webhook.py:129 @ 863e313`)的语义是"按解析出的
每个地址族各建一个套接字",只解析出 IPv4 时只建 IPv4 是正确行为。同文件其余用例全通过。

**这条已进 `CLAUDE.md` 的"已知环境限制",后续轮次不必重新排查。**

## 4. 子代理各自的实跑(与主线批次有重叠,单独记录)

各精读子代理在自己切片上另跑了针对性测试,均在基线 venv 上执行:

| 切片 | 实跑 | 结果 |
|---|---|---|
| cron scheduler 前半 | 5 文件 | 97 passed |
| cron scheduler 后半 | 7 文件 / 164 例 | 全通过 |
| cron jobs | `test_jobs.py` + `test_execution_ledger.py` | 84 passed |
| cron catalogs | 3 文件 | 36 passed |
| status / 运行态 | 7 文件 | 101 passed |
| authz / pairing | 11 文件 | 111 passed |
| delivery | 13 文件 | 127 passed |
| shutdown | 6 文件 | 40 passed |
| kanban / hooks | 11 文件 | 44 passed |
| slash A/B/C | 多批 | 全通过 |
| webhook 验签 | `TestValidateSignature` 9 例 + 限流/集成 5 例 | 全通过 |

## 5. 测试作为规格:本轮最值得引用的几条

### 5.1 三条"把 bug 固化成规格"的测试(本轮头等发现的共同形态)

这是本轮最重要的测试学教训:**下面三处的测试都通过,而被测机制在生产中不工作。**
它们不是测试写错了,而是测试**用一个生产中不存在的对象形状/状态**去测。

1. **`tests/gateway/test_shutdown_flush.py:49-57`** 用 `MagicMock` 手工挂上
   `session_id` 属性再去测 `recover_pending_to_db`。而真实 `MessageEvent`
   (`gateway/platforms/base.py:2054 @ 863e313`,AST 全字段枚举)**没有** `session_id`,
   于是生产路径恒走 `continue`(`gateway/shutdown_flush.py:242 @ 863e313`)。
   测试测的是一个生产中不存在的对象形状。

2. **`tests/gateway/test_dead_targets.py:4`** 的模块 docstring 明写
   "Covers the full lifecycle through the real ``DeliveryRouter.deliver()`` path" ——
   而 `deliver()` 全仓零生产调用点(`grep -rn "\.deliver(" --include=*.py .`
   只命中该测试文件的 :79/:85/:102)。**测试给了虚假的接线信心。**

3. **`tests/gateway/test_scale_to_zero_watcher.py:38`** 把 `r._background_tasks = set()`
   置空,并 monkeypatch 掉 `_scale_to_zero_is_idle`(`:42`);而生产中该集合被
   `_spawn_supervised` 塞进 8+ 个永不结束的常驻 watcher
   (`gateway/run.py:11611 @ 863e313`)。同文件的 `test_bg_work_blocks_idle_via_
   background_tasks`(`:65-83`)只放一个任务,证明的正是"有任务 ⇒ 非 idle"这个
   **当前实现的**语义 —— 它把 bug 写成了规格。

**可迁移结论:测试通过 ≠ 机制在生产中工作。** 判据要加一条:
**测试构造的输入对象,其形状必须与生产构造点一致。** 用 `MagicMock` 补字段、
把注册表置空、monkeypatch 掉被测谓词,三者都会让测试与生产脱钩。
R7 的 `memory_monitor.py`(有测试、零调用点)是这条规律的第一例,本轮又添三例。

### 5.2 把安全属性写成断言的正例

- `tests/gateway/test_status_phrases.py:16` 断言 `classify_status_context` 的
  `tool_name` / `preview` / `args` 三个参数**不被使用** —— 把"状态短语不泄露工具参数"
  这条安全属性钉成了可执行规格。**签名看不出来的约束,只能靠测试表达。**
- `tests/gateway/test_pairing.py` 双重钉住"配对码明文不落盘"。
- `tests/gateway/test_approvals_command.py::test_gateway_rejects_non_admin_persistent_
  approval_change` 钉住 `/approvals` 的二次鉴权。

### 5.3 R7B「让文档可执行」规律的再验证

R7B 结论:relay 有 `tests/gateway/relay/test_contract_doc_conformance.py`,于是它的
契约文档全仓最准。**本轮在 R7C 范围内检索同类"文档即测试",结果为零** ——
`gateway/` 外围面与 `cron/` 都没有任何把文档写进断言的测试。

对照本轮 ▲ 的分布:`cron-internals.md`、`gateway-internals.md`、
`ADDING_A_PLATFORM.md`、`environment-variables.md` 全部无此类测试,全部贡献了 ▲。
**规律第三次成立。**

一条尖锐的对照(webhook 验签簇,详见 `notes/r7c-raw-webhook-signing-docgap.md`):
三次外部贡献者 PR 各带大量测试、**各带零文档**;文档只在维护者亲自跟进那一次被补。
**测试覆盖率与文档覆盖率是两个独立指标 —— 除非把文档写进断言。**

## 6. 测试缺口(本轮点名,供后续轮次或上游参考)

- `cron/scripts/classify_items.py`:**零测试覆盖**、零 Python 调用点。
- `gateway/response_filters.py`:4 个公开函数只有 2 个有直测。
- `gateway/status_phrases.py:87-100` 的 `_relative_path_under` 路径沙箱:
  **无负例测试**(4 个用例里没有 `/etc/passwd` 或 `../../secrets`)。
- 关停看门狗与 systemd `TimeoutStopSec` 的**相对时序**无测试(正是 ▲ 的所在)。
- Svix 验签:无 `whsec_` 前缀密钥用例、无超窗(replay)用例。
- `tests/cron/test_suggestions.py:130-135` 的 `len(created) == len(CATALOG)`
  在 catalog 增至 6 条时会假失败(下一行已用 `min(...)` 想到上限,这一行没有)。
