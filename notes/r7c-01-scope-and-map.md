# r7c-01 · R7C 范围锚定、分层决策与主线亲核发现

> 底稿。基线 `863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。
> 本文件是 R7C 的主线卷:锚定范围、记录增删与分层决策、收录**主线亲自核验**的发现
> (与子代理底稿 `r7c-raw-*` 互为交叉校验)。

## 1. 范围锚定

以台账 `data/ledger.tsv` 的 `round=R7C` 为准:**47 个文件 / 28,282 行**。

**与磁盘逐文件复核一致**(核验脚本对每个路径 `wc -l`,零缺失、行数加总相等):

```
$ awk -F'\t' '$5=="R7C"{print $1}' data/ledger.tsv | while read f; do
    wc -l < "/home/user/hermes-agent/$f"; done | awk '{s+=$1;c++} END{print c, s}'
47 28282
```

**范围就是"其余的 gateway"这一判断也已证实**——`gateway/`(除 `platforms/`、`relay/` 两个
R7B 子树外)的全部条目按轮次统计:

```
$ awk -F'\t' '$1 ~ /^gateway\// && $1 !~ /^gateway\/(platforms|relay)\// {print $5}' \
    data/ledger.tsv | sort | uniq -c
     16 R7
     36 R7C
      1 -        ← gateway/assets/telegram-botfather-threads-settings.jpg(L4 有理由排除)
```

即 R7 的 16 个 + R7C 的 36 个 = `gateway/` 顶层与 `assets/`、`builtin_hooks/` 的全部
非二进制文件,**无遗漏、无第三轮次**。加 `cron/` 全部 11 个文件 = 47。

### 1.1 增删决策:不增不删

任务简报允许调整范围。**本轮维持台账原样,不增不删**,理由:
- `gateway/` 侧已证实为精确补集(上表),再增就会侵入 R7/R7B 已完成的切片;
- `cron/` 已全部纳入(11/11),本轮主题"定时调度"没有留在范围外的文件;
- 唯一被排除的 `gateway/assets/telegram-botfather-threads-settings.jpg` 是一张
  BotFather 设置截图,L4「有理由排除」判定成立(二进制图片,无可读语义)。

## 2. 分层决策:10 个文件 L2 → L1

任务简报要求本簇达成 **L1 完成标准**。但开轮时台账里有 10 个 R7C 文件被 `assign_layers.py`
归为 **L2(结构级理解)**:

| 文件 | 行数 | 原 layer |
|---|---:|---|
| `cron/scheduler.py` | 4428 | L2 |
| `cron/jobs.py` | 2746 | L2 |
| `cron/blueprint_catalog.py` | 713 | L2 |
| `cron/lifecycle_guard.py` | 565 | L2 |
| `cron/scheduler_provider.py` | 357 | L2 |
| `cron/executions.py` | 280 | L2 |
| `cron/suggestions.py` | 260 | L2 |
| `cron/suggestion_catalog.py` | 154 | L2 |
| `cron/__init__.py` | 42 | L2 |
| `gateway/assets/status_phrases.yaml` | 52 | L2 |
| **合计** | **9,597** | |

**决策:全部提升为 L1**,并在 `scripts/assign_layers.py` 里落成规则(而非手改台账),
理由三条:

1. **本轮主题就是它们**。轮次名为"网关外围面与**定时调度**",而 `cron/` 九个 `.py`
   正是定时调度的全部实现。把主题本体留在 L2,与「达成 L1 完成标准」直接冲突。
2. **先例**:R6 轮为同一理由把 8 个 memory backend 的实现文件从 L2 提到 L1
   (commit `141a06e`),R5 轮提了 4 个 R4-structure 文件。分层是"计划学到什么程度",
   随轮次目标修订是制度内动作,需在当轮报告说明——本节即说明。
3. **yaml 一并提升**:`status_phrases.yaml` 只有 52 行,是 `status_phrases.py` 的**数据本体**,
   读 `.py` 不读它等于没读懂短语库。分开归层没有意义。

提升后 R7C 的 47 个文件**全部为 L1**,本簇无 L2 残留。

## 3. 主线亲核发现

以下为**主线亲自读码核验**的条目,不经子代理。它们的共同来源是一次交叉检查:
`gateway/platforms/ADDING_A_PLATFORM.md` 的「Built-in Path」16 步接入清单里,
有 **3 步直接点名 R7C 范围内的文件**(§8 `cron/scheduler.py`、§11
`gateway/channel_directory.py`、§12 `hermes_cli/status.py`)。R7B 已证明这份文档是
全仓 ▲ 高发区,于是主线逐步对表。结果:**点名 R7C 文件的三步,两步已经不可执行,
第三步指向的代码里藏着一个真 bug**。

### 3.1 ▲ C-1 —— 接入清单 §8「Cron Delivery」的落点不存在

**文档**(`gateway/platforms/ADDING_A_PLATFORM.md:256-266 @ 863e313`):

```markdown
## 8. Cron Delivery (`cron/scheduler.py`)

Add to `platform_map` in `_deliver_result()`:

```python
platform_map = {
    ...
    "your_platform": Platform.YOUR_PLATFORM,
}
```

Without this, `cronjob(action="create", deliver="your_platform", ...)` silently fails.
```

**代码**:`cron/` 全目录**没有任何 `platform_map`**:

```
$ grep -rn "platform_map" cron/
$ echo $?
1
```

`_deliver_result` 确实存在(`cron/scheduler.py:1467 @ 863e313`),但它不做平台名到枚举的
映射,而是把整件事委托给 `_resolve_delivery_targets`:

`cron/scheduler.py:1478-1479 @ 863e313`
```python
    targets = _resolve_delivery_targets(job)
    if not targets:
```

真正的接入落点是**模块级常量表** `_HOME_TARGET_ENV_VARS`(`cron/scheduler.py:264 @ 863e313`
起,内建平台名 → home channel 环境变量名):

`cron/scheduler.py:278 @ 863e313`
```python
    "qqbot": "QQBOT_HOME_CHANNEL",
```

**裁决:▲ 证伪,且是"照做也做不到"的那一类**。读者按 §8 去 `_deliver_result()` 里找
`platform_map`,会找不到任何可改之处。文档给的是重构前的落点。

**附带的第二层失实**:§8 声称不改就会 "silently fails"。对**插件平台**这句话也不成立——
插件平台根本不需要改 `cron/scheduler.py`,它们从平台注册表拿投递环境变量:

`cron/scheduler.py:1033-1040 @ 863e313`
```python
    Built-in platforms are in ``_HOME_TARGET_ENV_VARS``; plugin platforms are
    resolved from the platform registry.
    """
    name = platform_name.lower()
    env_var = _HOME_TARGET_ENV_VARS.get(name)
    if env_var:
        return env_var
    return _plugin_cron_env_var(name)
```

`cron/scheduler.py:1092-1095 @ 863e313`
```python
        from gateway.platform_registry import platform_registry
        for entry in platform_registry.plugin_entries():
            if entry.cron_deliver_env_var and entry.name not in _HOME_TARGET_ENV_VARS:
                yield entry.name
```

即:**内建平台改一张表;插件平台改零行网关代码**。这与 R7B 归纳的"三条接入血统成本
曲线截然不同"完全一致,而 §8 把两者混为一谈。

### 3.2 ▲ C-2 —— 接入清单 §11「Channel Directory」的落点不存在

**文档**(`gateway/platforms/ADDING_A_PLATFORM.md:304-312 @ 863e313`):

```markdown
## 11. Channel Directory (`gateway/channel_directory.py`)

If your platform can't enumerate chats (most can't), add it to the
session-based discovery list:

```python
for plat_name in ("telegram", "whatsapp", "signal", "your_platform"):
```
```

**代码**:`gateway/channel_directory.py` 里**没有这个循环**,整个文件只有一处提到
`telegram`,而且是一句给用户看的说明文字:

```
$ grep -n "signal\|telegram\|whatsapp" gateway/channel_directory.py
635:    lines.append('Bare platform name (e.g. "telegram") sends to home channel.')
```

`gateway/channel_directory.py:635 @ 863e313`
```python
    lines.append('Bare platform name (e.g. "telegram") sends to home channel.')
```

**裁决:▲ 证伪**。文档给出的代码片段在被点名的文件里不存在,该步同样不可执行。

### 3.3 ▲ C-3 —— 同一清单 §9 也是同一种腐烂(旁证)

`gateway/platforms/ADDING_A_PLATFORM.md:271-275 @ 863e313` 让读者去 `tools/send_message_tool.py` 的
`send_message_tool()` 里改 `platform_map`。同样零命中:

```
$ grep -n "platform_map" tools/send_message_tool.py
$ echo $?
1
```

该文件实际用的是一长串 `if platform == Platform.X:` 的分派
(`tools/send_message_tool.py:798,853,872,917,934,950,966,992,1034 @ 863e313` 等)。
此条锚点在 R7C 范围外(`tools/`),**仅作旁证列出、不计入本轮定案数**——但它把 C-1/C-2
从"两处笔误"抬升为**一次统一重构后整份清单未同步**的证据:`platform_map` 这个名字
曾经同时存在于 cron 投递与 send_message 工具两处,重构后两处都没了,文档两处都还在。

### 3.4 bug 候选 C-4 —— `hermes status` 读错 QQBot home channel 环境变量(back-compat 分支写反且恒假)

这是顺着接入清单 §12(`hermes_cli/status.py`)查出来的**真缺陷**,不是文档问题。

**全仓的规范名是 `QQBOT_HOME_CHANNEL`,`QQ_HOME_CHANNEL` 是已弃用的旧名**——
配置装载侧说得很明确:

`gateway/config.py:2432 @ 863e313`
```python
        qq_home = getenv("QQBOT_HOME_CHANNEL", "").strip()
```

`gateway/config.py:2441 @ 863e313`
```python
                    "QQ_HOME_CHANNEL is deprecated; rename to QQBOT_HOME_CHANNEL "
```

`cron/scheduler.py` 把这层关系表达得最干净——**主名 → 旧名**的映射,读不到主名才回落:

`cron/scheduler.py:283-289 @ 863e313`
```python
# Legacy env var names kept for back-compat.  Each entry is the current
# primary env var → the previous name.  _get_home_target_chat_id falls
# back to the legacy name if the primary is unset, so users who set the
# old name before the rename keep working until they migrate.
_LEGACY_HOME_TARGET_ENV_VARS = {
    "QQBOT_HOME_CHANNEL": "QQ_HOME_CHANNEL",
}
```

`cron/scheduler.py:1043-1052 @ 863e313`
```python
def _get_home_target_chat_id(platform_name: str) -> str:
    """Return the configured home target chat/room ID for a delivery platform."""
    env_var = _resolve_home_env_var(platform_name)
    if not env_var:
        return ""
    value = os.getenv(env_var, "")
    if not value:
        legacy = _LEGACY_HOME_TARGET_ENV_VARS.get(env_var)
        if legacy:
            value = os.getenv(legacy, "")
    return value
```

**而 `hermes_cli/status.py` 把这两个名字用反了**:

`hermes_cli/status.py:483 @ 863e313`
```python
        "QQBot": ("QQ_APP_ID", "QQ_HOME_CHANNEL"),
```

`hermes_cli/status.py:491-496 @ 863e313`
```python
        home_channel = ""
        if home_var:
            home_channel = os.getenv(home_var, "")
        # Back-compat: QQBot home channel was renamed from QQ_HOME_CHANNEL to QQBOT_HOME_CHANNEL
        if not home_channel and home_var == "QQBOT_HOME_CHANNEL":
            home_channel = os.getenv("QQ_HOME_CHANNEL", "")
```

两个缺陷叠在一起:

1. **主名取了旧名**:字典里 QQBot 的 `home_var` 是 `"QQ_HOME_CHANNEL"`(弃用名),
   而不是全仓规范名 `"QQBOT_HOME_CHANNEL"`。
2. **回落分支恒假**:`:495` 判 `home_var == "QQBOT_HOME_CHANNEL"`,但字典里唯一的
   QQBot 条目给出的 `home_var` 恒为 `"QQ_HOME_CHANNEL"`,该条件**永远不成立**——
   这三行是**死代码**。而且注释把方向写对了("renamed from QQ_HOME_CHANNEL to
   QQBOT_HOME_CHANNEL"),代码却按反方向实现:它试图从新名回落到旧名,可它的主名
   本来就是旧名。

**用户可见后果(happy path 就会踩到)**:安装向导写的是**新名**——

`hermes_cli/gateway.py:6132 @ 863e313`
```python
                save_env_value("QQBOT_HOME_CHANNEL", user_openid)
```

于是一个跑完向导、只设了 `QQBOT_HOME_CHANNEL` 的用户,`hermes status` 里 QQBot 那一行
**不会显示 home channel**(`os.getenv("QQ_HOME_CHANNEL")` 为空,死分支又救不回来),
尽管网关与 cron 投递都能正常读到它。即 **status 面板与真实运行状态不一致**,
而 status 面板恰恰是用户用来确认"我配对了没有"的地方。

对照组:`hermes_cli/doctor.py` 做对了,它按 (旧名, 新名) 成对登记迁移关系:

`hermes_cli/doctor.py:258 @ 863e313`
```python
    ("QQ_HOME_CHANNEL", "QQBOT_HOME_CHANNEL"),
```

**处置**:hermes-agent 只读,不修。作为学习产出记录。锚点文件 `hermes_cli/status.py`
在 R7C 范围外(属 `hermes_cli/` 桶),故**不计入本轮定案数**,以"跨簇发现"列入报告。

**这条同时给 R7B 移交的「`status.py` 描述矛盾」提供了落点**——详见 §4。

## 4. R7B 移交项「`status.py` 描述矛盾」的溯源问题

任务简报要求定案 R7B 移交的三项,其一是「`status.py` 描述矛盾」。**主线检索发现:
这一项在 R7B 的底稿里没有任何记录**,只在报告的下一轮建议里出现过一次:

```
$ grep -rn "status" notes/r7b-90-doc-conflict-rulings.md
$ echo $?
1
$ grep -rn "status\.py" notes/ reports/round-7b-platform-integration.md | grep -i r7b
reports/round-7b-platform-integration.md:161:与 R7B 新增的三项(`status.py` 描述矛盾、五方言验签的运营文档缺口、审批解析器的
```

即:**该移交项只有标题、没有证据体**。它没有出现在 `notes/r7b-90` 的 24 条定案里,
也没有出现在任何 R7B 底稿中。

**处置**:不假装它有已知内容,按「重新独立取证」处理——本轮对**两个** `status.py`
分别取证(`gateway/status.py` 由子代理精读;`hermes_cli/status.py` 由主线核验,即 §3.4),
在 `notes/r7c-90` 里给出定案。**这条溯源缺口本身记为本项目的一次流程教训**:
移交项若只写标题不写证据,下一轮要么重做、要么误传;制度上应要求移交项至少附
"锚点文件 + 一句话现象"。已写入本轮报告的建议。

## 5. 本轮两项修订(任务簿指定)

### 5.1 修订一:「自检 grep 只扫 `gateway/`」表述更正

R7B 的头条叙述里说 `ADDING_A_PLATFORM.md` 自带的自检 grep "只扫 `gateway/`"。
主线复核:**扫描集是六个路径**,不止一个。

`gateway/platforms/ADDING_A_PLATFORM.md:400-404 @ 863e313`
```bash
# Grep for your platform name to find any missed integration points
grep -r "telegram\|discord\|whatsapp\|slack" gateway/ tools/ agent/ cron/ hermes_cli/ toolsets.py \
  --include="*.py" -l | sort -u
# Check each file in the output — if it mentions other platforms but not yours, you missed it
```

同时更正第二处小失准:该 grep **不在 §16**。§16 是 "Tests"
(`gateway/platforms/ADDING_A_PLATFORM.md:372 @ 863e313`),自检 grep 在其后的独立小节
"## Quick Verification"(`:392 @ 863e313`)。

**结论不变,理由要点明**:六个路径里**依然没有 `plugins/`**,而 R7B ▲B-3 的三处失效
路径指向的正是 `plugins/platforms/*/adapter.py`。扫描集比原叙述宽,却恰好绕开了唯一
相关的目录——"它发现不了自己那条 ▲"成立。

**更正落点(四处,全部已改)**:
- `notes/r7b-90-doc-conflict-rulings.md` B-3 定案段(附完整代码块与理由)
- `notes/r7b-90-doc-conflict-rulings.md` §5 第 1 条
- `reports/round-7b-platform-integration.md` 头条段
- `chapters/r7b-platform-integration.md` §4 对应段

任务簿只点名了前两处中的 §5 与报告头条;主线**扩展到四处**,理由:同一句话在底稿、
报告、成品章三层各出现一次,只改两处会让仓库自相矛盾,而成品章是 R12 蓝图正文,
留错代价最大。

### 5.2 修订二:测试环境重建步骤并入 `CLAUDE.md`

把 `notes/r7b-95 §1` 的发现固化进 `CLAUDE.md` 的「测试环境」一节:
`aiohttp` 不在 `[dev]` extra 而在 `messaging` 等平台 extra 里
(`pyproject.toml:176 @ 863e313`),而 `gateway/platforms/api_server.py`、`webhook.py`、
`whatsapp_cloud.py` 直接 import 它,只装 `[dev]` 会让约 20 个测试文件在**收集阶段**
就 ImportError(容易被误读成"测试挂了")。

同时把 R7B 查实的**环境限制**一并写入,避免后续轮次重复排查:本类云端容器无 IPv6
协议族,`tests/gateway/test_webhook_adapter.py::TestDualStackBind::
test_default_bind_serves_both_families` 必然失败,而被测代码
`DEFAULT_HOST = None`(`gateway/platforms/webhook.py:129 @ 863e313`)在只解析出 IPv4 时
只建 IPv4 **是正确行为**。

本轮已按新步骤重建 venv 并验证可用。
