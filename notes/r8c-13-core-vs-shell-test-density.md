# r8c-13 · 结清 [→R8C/R9]:「共享核心 + N 个薄壳」的测试盲区是不是全仓通病

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块,锚点置于块前。
> 实跑环境:venv `/home/user/hermes-venv`,87 个包。

## 0. 移交原文

R8A 在 `notes/r8a-raw-pairing-and-config-cmd.md:1388` 留下:

> 3. **[→R8C/R9]「共享核心 + N 个薄壳」的测试盲区是否为全仓通病**
>    - 锚点:`tests/gateway/test_pairing.py`(28 用例,store 层)
>      vs `tests/hermes_cli/test_pairing.py:8` + `tests/hermes_cli/test_dashboard_admin_endpoints.py:256`
>      (合计 4 用例,壳层)
>    - 现象:核心测密、壳测稀,而唯一的行为分叉恰在壳里且零覆盖。
>      建议在 webhook / mcp / cron 等同样是「CLI + GUI 双壳」的子系统上重复这次对照,
>      验证这是 pairing 个例还是仓库级模式。

**本轮结论:是仓库级模式,不是 pairing 个例。四个子系统的「核心 : GUI 壳」比落在 20:1 到 35:1。**

---

## 1. 口径(先钉死,否则这张表没有意义)

用 pytest 的收集器数,不用 `grep -c 'def test_'`——后者数不到参数化用例,也数不清类内外。

```verify
$ cd /home/user/hermes-agent
$ /home/user/hermes-venv/bin/python -m pytest <目录> -k "<关键词>" --collect-only -q | tail -1
```

三层的界定:

| 层 | 目录 | 说明 |
|---|---|---|
| **核心** | `tests/gateway` + `tests/cron`(mcp 另见下)| 子系统自己的实现层 |
| **CLI 壳** | `tests/hermes_cli`,`-k "<kw> and not dashboard and not web_server"` | `hermes <cmd>` 那一侧 |
| **GUI 壳** | `tests/hermes_cli` + `tests/dashboard`,`-k "<kw> and (dashboard or web_server or api)"` | dashboard HTTP 那一侧 |

**这个口径有一个已知的坑,本轮踩到并修正了**:第一次跑时把 mcp 的"核心"也放在
`tests/gateway + tests/cron` 下,得数 **17**,于是表面上出现了"mcp 反过来了、壳比核心密"的
反常结果。**那是口径错,不是发现**——mcp 的核心测试根本不住在那两个目录:

```console
$ grep -rl "mcp" tests/ --include=*.py | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -4
     61 tests/tools
     33 tests/hermes_cli
     17 tests/agent
     10 tests/gateway
```

改用 `tests/tools + tests/gateway` 后 mcp 核心得 **455**,与其余三个同形。
**记下来是因为这正是 CLAUDE.md「shell 命令即证据」那条要防的形状**:
一条口径错的命令会给出一个看起来很有意思、实则相反的结论。

---

## 2. 实测结果

| 子系统 | 核心 | CLI 壳 | GUI 壳 | 核心 : GUI 壳 |
|---|---|---|---|---|
| pairing | 64 | 9 | **3** | 21 : 1 |
| webhook | 106 | 14 | **3** | 35 : 1 |
| mcp | 455 | 93 | 23 | 20 : 1 |
| cron | 439 | 33 | 13 | 34 : 1 |

**四个子系统,没有一个例外。** R8A 在 pairing 上看到的形状是仓库级的。

**GUI 壳那一列尤其值得盯**:pairing 和 webhook **各只有 3 个用例**,而且它们全部住在
同一个文件的同一个类里:

```console
tests/hermes_cli/test_dashboard_admin_endpoints.py::TestPairingEndpoints::test_approve_pending_request_id
tests/hermes_cli/test_dashboard_admin_endpoints.py::TestPairingEndpoints::test_pairing_is_isolated_per_profile
tests/hermes_cli/test_dashboard_admin_endpoints.py::TestPairingEndpoints::test_unknown_profile_is_rejected
tests/hermes_cli/test_dashboard_admin_endpoints.py::TestWebhookEndpoints::test_create_webhook_persists_script
tests/hermes_cli/test_dashboard_admin_endpoints.py::TestWebhookEndpoints::test_enable_platform_starts_gateway_restart
tests/hermes_cli/test_dashboard_admin_endpoints.py::TestWebhookEndpoints::test_enable_platform_reuses_inflight_gateway_restart
tests/hermes_cli/test_dashboard_admin_endpoints.py::TestMcpEndpoints::test_stdio_env_is_redacted_on_read
```

**`tests/hermes_cli/test_dashboard_admin_endpoints.py` 一个文件共 31 个测试函数,
要覆盖 dashboard 的整个管理面——而这个面有 123 条已注册路由。**

---

## 3. 为什么这个形状会持续存在(不只是"没写够")

**核心层好测,壳层难测。** 核心是纯函数与状态机,给个临时目录就能跑;
壳层要起 ASGI 应用、要伪造鉴权、要处理异步。**成本差一个数量级,于是覆盖也差一个数量级。**

**但危险恰恰倒过来:分叉在壳里,不在核心里。** 本轮定案的六条 ■ 里,
**有四条的失效点在壳层而不在核心层**:

- ■-R8C-02 / ■-R8C-03:`/api/fs/*` 与 `/api/files/*` 的守卫差异——两个壳,一个核心(文件系统)。
- ■-R8C-05:`PUT /api/config` 与 `PUT /api/env` 的名单差异——两个壳,一个核心(配置写入)。
- ■-R8C-06:`_KNOWN_DELIVERY_PLATFORMS` 与 `_HOME_TARGET_ENV_VARS` 的表差异——同一核心的两张表。
- ◇-R8C-a:`PairingStore()` 与 `PairingStore(profile="default")` 的三处不等价——
  一个核心,两种调用约定。

**共同形状是同一个:核心只有一份,所以核心的测试测的是"这一份对不对";
而分叉发生在"谁怎么调它",那正好是测试最稀的那一层。**

**所以这不是覆盖率不够的问题,是覆盖率的分布和风险的分布反着来。**

---

## 4. 定案

**结清 [→R8C/R9] 第 3 条,负结论不成立的方向**:R8A 怀疑的"这可能是 pairing 个例"
**被证伪**——四个子系统全部呈现同一形状,核心:GUI 壳比 20:1 至 35:1,
GUI 壳在 pairing / webhook 上各只有 3 个用例且同住一个文件的一个类里。
**记为 ◇-R8C-b(仓库级模式,信息类,不记 ■)。**

**不判 ■ 的理由**:"测得少"本身不是缺陷,它是成本约束下的合理取舍;
判 ■ 需要指出一个具体的失效,而那些失效已各自单独立案(§3 列的四条)。
**把"测试稀"本身记成缺陷会稀释 ■ 的含义。**

---

## 5. 本段未覆盖 / 存疑

| 项 | 锚点 | 一句话现象 |
|---|---|---|
| `-k` 关键词匹配是近似口径 | `tests/hermes_cli/test_dashboard_admin_endpoints.py`(31 个测试函数) | 按测试**名字/路径**含关键词来归层,会漏掉"测了 pairing 但名字里没有 pairing"的用例,也会误收名字碰巧撞上的;**没有做按导入关系的精确归属**,所以表里的数是量级正确、个位数不保证 |
| "123 条路由里有几条真被测过"未测 | `hermes_cli/web_server.py` 的 135 条内联路由 + 14 处 `include_router` | 比"用例数"更能说明问题的是**路由覆盖率**,本轮没做——需要给 TestClient 挂一层记录实际命中路径的钩子 |
| 只对照了 4 个子系统 | R8A 建议的 webhook / mcp / cron 已做,pairing 是原案 | skills / tools / profiles / sessions 这几个同样是"CLI + GUI 双壳"的子系统**未对照** |
