# r8a-95 · 配套测试作为行为规格

本轮把 R8A 覆盖的 15 个文件对应的测试当作**行为规格**跑了一遍并读了关键几支。
溯源约定同 `notes/r8a-01`。

---

## 1. 规格集怎么圈的,以及跑出了什么

R8A 的模块被全仓广泛 import(尤其 `hermes_cli.config`),按"谁 import 了它"取集会得到
**399 个文件** —— 那不是规格集,那是"几乎所有测试"。故改用两条更窄的判据取并集:

1. import 了 R8A 的**窄模块**之一(`config_defaults` / `tools_config` / `mcp_config` /
   `moa_config` / `config_migrations` / `env_loader` / `skills_config` / `fallback_config` /
   `secret_prompt` / `hermes_cli.commands` / `hermes_cli.status` / `hermes_cli.pairing`)
   —— **不含**无处不在的 `hermes_cli.config`,单凭它入选没有区分度;
2. 文件名本身就指向本簇主题(`test_config*` / `test_*command*` / `test_*status*` /
   `test_*pairing*` / `test_*migration*` / `test_env_loader*` / `test_*secret*` …)。

并集 **170 个文件**,分布:`tests/hermes_cli/` 68、`tests/gateway/` 27、`tests/cli/` 16、
`tests/tools/` 12、`tests/agent/` 11、`tests/tui_gateway/` 8,其余零散。

**结果:170 文件 / 3,183 用例全部通过,0 失败,76.1 秒(8 worker)。**

```
=== Summary: 170 files, 3183 tests passed, 0 failed (100% complete) in 76.1s (8 workers) ===
```

R7B/R7C 两轮都遇到的 `TestDualStackBind`(容器无 IPv6)**不在本轮规格集内**,故本轮
零环境性失败,无需援引 `CLAUDE.md` 里那条已知环境限制。

**跑了两次,第二次是事故后的复核。** 定稿阶段发现基线被子代理写脏过一次
(`package-lock.json`,详见 `reports/round-8a-*` §0),恢复后**重跑了同一套规格集**:

```
=== Summary: 170 files, 3183 tests passed, 0 failed (100% complete) in 69.0s (8 workers) ===
```

**文件数、用例数、失败数与第一次逐位相同**(仅耗时 76.1s → 69.0s),
确认恢复干净、测试环境未受影响。这也是"基线完整性"值得做成脚本关卡的又一个理由:
**出事之后,你需要一个能证明"已经恢复原状"的动作,而不是只能靠印象。**

---

## 2. 值得抄走的规格:迁移的"floor 不变量"

`config_migrations` 没有独立测试文件,它的规格藏在 `tests/hermes_cli/test_config.py`
(全文 64 个用例)里。其中两支是**真正的不变量测试**,不是例子测试:

`tests/hermes_cli/test_config.py:687 @ 863e313`

```python
    def test_registry_has_no_targets_below_floor(self):
```

这一支保证**迁移注册表里不会残留低于支持下限的步骤** —— 它不测"某次迁移做对了",
而是测"这张表本身的形状合法"。配合另一支:

`tests/hermes_cli/test_config.py:765 @ 863e313`

```python
    def test_at_or_above_floor_migrates_identically_to_pre_floor(
```

它断言**砍掉 v12 以下的步骤之后,v12 及以上的配置迁移结果与砍之前逐字相同** ——
也就是把"这次删代码没有改变任何仍受支持路径的行为"变成了一条可执行的断言。

**重实现要点**:凡是"逐版本升级"的迁移表,值得配两类测试——
(a) 表的**形状不变量**(无跳过、无低于下限、严格升序);
(b) **删除安全性**:淘汰老步骤时,证明受支持区间的输出不变。
只测单个 `_migrate_to_N` 做了什么,拦不住这两类事故。

---

## 3. 为什么 QQBot 那个死分支能活下来:规格里根本没有它

`notes/r8a-01` §3.1 定案的死分支,**不是测试写错了,是这条行为从来没有被测过**。

- `tests/hermes_cli/test_status.py` 全文 **10 个用例**,主题分别是:
  不打印 Tavily key 值、Termux 下跳过 systemctl、Vercel 后端契约、
  OAuth 授权存储的显示、以及**四支抗崩溃测试**(import 失败 ×2 / 函数抛异常 /
  函数返回 None,都不能让 `show_status` 崩)。**没有任何一支断言平台表那一行的内容。**
- 全仓测试里提到 `QQ_HOME_CHANNEL` 的只有一处:

`tests/hermes_cli/test_doctor.py:1383 @ 863e313`

```python
            "QQ_HOME_CHANNEL",
```

而它出现在一个 `monkeypatch.delenv` 的清理列表里 —— 该测试**删掉**这个变量来隔离环境,
**从不断言**它。

**结论:`hermes status` 平台表的 home 频道解析,14 个平台一个都没有行为规格。**
这比"有测试但测错了"更值得记:R7C 定案过"测试会把 bug 固化成规格"(用 MagicMock
补出不存在的字段),本轮这条是另一端 —— **零规格区**。
死分支能活下来不需要一个骗人的测试,只需要没有测试。

**判据(可迁移)**:一段代码里出现"向后兼容"分支,而它的模块测试全是抗崩溃测试
(assert 不抛异常)而非行为断言,那么这个兼容分支**极可能从未被执行过**。
抗崩溃测试的覆盖率好看,但它对"值对不对"零信息。

---

## 4. 两个装载器的分歧同样没有规格

`notes/r8a-01` §2.1 那条"同一份 config.yaml、两个装载器、合并语义不同",
在测试里的情形比"没测"更值得琢磨:**这条性质被测了,而且有一支以它命名的用例,
但测在了唯一做对了的那一层上。**

先看两个装载器各自的测试如何被组织。`tests/hermes_cli/test_config_env_expansion.py`
同时覆盖两边,但分在两个类里,各自只验证**自己这一侧**的 `${VAR}` 展开:

`tests/hermes_cli/test_config_env_expansion.py:93-94 @ 863e313`

```python
class TestLoadCliConfigExpansion:
    """Verify that load_cli_config() also expands ${VAR} references."""
```

这个 `also` 说明作者是**有意在核对两侧的一致性**的 —— 但核对的是"环境变量展开"
这一条性质,没有核对合并语义。

再看那支以"保住同级键"命名的用例:

`tests/hermes_cli/test_managed_scope_cli_config.py:58 @ 863e313`

```python
def test_cli_config_managed_leaf_preserves_user_siblings(homes):
```

`tests/hermes_cli/test_managed_scope_cli_config.py:59 @ 863e313`

```python
    """Managed display.skin must not wipe a user's other display.* prefs."""
```

它构造的场景是:用户配置写 `display: {skin, show_reasoning}`,管理员配置写 `display: {skin}`,
断言管理员的 `skin` 生效**且用户的 `show_reasoning` 存活**:

`tests/hermes_cli/test_managed_scope_cli_config.py:70-71 @ 863e313`

```python
    assert display.get("skin") == "charizard"  # managed wins
    assert display.get("show_reasoning") is True  # user sibling preserved
```

**关键在于这里的"基底"是谁**:被覆盖的是**用户配置**,覆盖方是 **managed 层**,
走的是 `apply_managed_overlay` 的叶级合并 —— 那条路径是**对的**。
而出问题的是更前面一步:**内置默认值 ← 用户配置**,走 `dict.update`。
用户配置在这支测试里始终是基底,从来不是"覆盖方",所以那条浅合并路径
**在这支专门测同级键存活的用例里也没被走到**。

**这才是它能长期存活的原因**:不是没人在乎这条性质,而是**在乎它的那支测试
恰好站在了正确的那一侧**。覆盖率报告上,`load_cli_config` 是被测过的;
"同级键存活"是被测过的;两者都绿。

**重实现要点(两条)**:
1. 当系统里存在同一份输入的两个解释器(两个装载器、服务端与客户端各一份校验),
   必须有一支**双读一致性**测试,直接断言二者对同一输入产出相同结果。
   这类测试单看哪一边都写不出来,只能显式跨边界写。
2. 当一条性质(如"覆盖不得清除同级键")在**多个层**上都该成立,
   测试必须**逐层枚举**,而不是挑一层测了就算数。
   按"性质 × 层"做矩阵,空格子一目了然;按"层"分文件写测试,空格子看不见。

---

## 5. 本轮"文档即测试"检索结果

在 R8A 范围内检索 relay 那种"拿文档当断言源"的测试(`test_contract_doc_conformance.py`
一类),**结果为零**。这与本轮 ◇ 条目的分布吻合:**856 个配置键里有 105 个在全部文档面上
零提及**(见 `notes/r8a-90` ◇-1;那里也记录了为什么"覆盖率百分比"这个说法本轮被推翻),
而没有任何自动关卡把 `DEFAULT_CONFIG` 与文档对表 —— 全靠人工维护。
反观**环境变量那一侧零缺口**,靠的也不是自动化,是 `OPTIONAL_ENV_VARS` 每条自带
`description` 字段这一**结构性耦合**(定义与说明写在同一个字面量里,想漏都难)。

**顺带补一条本轮的自我更正**:这里原本写的是"覆盖率 87.7%"。
后来发现该数字来自**叶子名回退匹配**,而 `enabled` / `timeout` 这类叶子名在文档里到处都是,
严重高估;换成点分全路径匹配则得 0.0%(文档写 YAML 块,压根不用点分写法)。
**两个边界都不可用,故本卷与报告一律只报那个确定成立的数:105 个键零提及。**

**这是本轮最可迁移的一条设计原则**,详见成品章 §4。
