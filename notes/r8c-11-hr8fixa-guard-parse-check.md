# r8c-11 · H-R8FIX-a 定案 —— 给守卫补解析检查,破不破坏「全新安装 / 空文件」语义

> 溯源约定:`路径:行号 @ 863e313` + 代码原文块,锚点置于块前。
> 实跑环境同 `notes/r8c-10`(venv 87 包)。

## 0. 移交原文与本轮结论

> **H-R8FIX-a** | R8C / R8D | `hermes_cli/config.py:3065`
> (`require_readable_config_before_write` 只 `stat()` + `read(1)`)+ `hermes_cli/auth.py:7329`
> H-7 重开后剩下的设计判断:**给该守卫补一道解析检查会不会破坏「全新安装 / 空文件」语义**?
> 五个裸写点里四个各自在收口之外补了检查,说明"补在收口里"可能才是对的落点,但没有验证过。
> **本卡未做运行时复现**(不改被测仓库、未建 venv)。

**本轮结论(实测,7 种输入逐一跑过):**

1. **不破坏。** 但前提是把判据写成"**解析会不会抛**",而不是"解析结果是不是非空字典"。
2. **只查"会不会抛"还不够。** 有一类输入解析得好好的,却照样触发那个静默清空——
   守卫会放行。完整判据是「**解析不抛 且 结果是 `None` 或 `dict`**」。
3. **补进收口是对的落点**,理由不是"四个调用方都在收口外补过",而是
   **收口自己已经正确处理了「全新安装」那一支**(`FileNotFoundError` 直接 `return`),
   补解析检查只是把同一个 `config_path` 多读一次,不引入新的信息需求。
4. **代价要写明**:会新拒一类此前放行的输入(带未知 YAML 标签的配置)。

---

## 1. 守卫现在做什么

`hermes_cli/config.py:3065 @ 863e313`

```python
def require_readable_config_before_write(config_path: Optional[Path] = None) -> None:
```

**「全新安装」这一支,守卫本来就处理对了**——文件不存在直接放行:

`hermes_cli/config.py:3070 @ 863e313`

```python
        config_path.stat()
```

`hermes_cli/config.py:3071 @ 863e313`

```python
    except FileNotFoundError:
```

`hermes_cli/config.py:3072 @ 863e313`

```python
        return
```

**「能不能读」这一支,只读一个字节**:

`hermes_cli/config.py:3080 @ 863e313`

```python
        with open(config_path, "rb") as f:
```

`hermes_cli/config.py:3081 @ 863e313`

```python
            f.read(1)
```

**一个字节读得出来,守卫就放行。** 而 ■-R8B-12 的输入——一个缩进坏掉的
`config.yaml`——第一个字节当然读得出来。守卫防的是"读不到",而事故是"读得到但解析不了"。

它要防的那个歧义,在 `read_raw_config` 里:解析失败返回 `{}`——

`hermes_cli/config.py:2962 @ 863e313`

```python
            _warn_config_parse_failure(config_path, e)
```

`hermes_cli/config.py:2963 @ 863e313`

```python
            return {}
```

——**和"文件不存在"返回的 `{}` 一模一样**。调用方读完再整文件覆盖,就把配置抹了。

---

## 2. 实测:7 种输入,现守卫 vs 两种候选判据

用 venv 里的 `hermes_cli.config.require_readable_config_before_write` 与
`utils.fast_safe_load`(即 `read_raw_config` 实际用的解析器)逐个跑:

```console
输入                     现守卫      只查解析会不会抛    查解析 + 必须 None-or-dict
------------------------------------------------------------------------------
缺席(全新安装)             放行        放行              放行
空文件(0 字节)            放行        放行              放行
只有注释                 放行        放行              放行
合法配置                 放行        放行              放行
坏缩进(■-R8B-12 的输入)   放行        拒绝              拒绝
非 dict 顶层(- a / - b)  放行        放行              拒绝
未知 YAML 标签            放行        拒绝              拒绝
```

**逐行读这张表,四个结论:**

**(a)「全新安装」不受影响。** 文件不存在时守卫在 `:3072` 就 `return` 了,
根本走不到解析那一步。移交项担心的第一件事**不成立**。

**(b)「空文件」也不受影响,而且理由值得写下来。**
`fast_safe_load("")` 返回的是 `None`,**不是抛异常**——YAML 里"空文档"是合法文档。
"只有注释"同理。所以只要判据是"抛不抛",空文件天然放行。
**如果有人把判据写成"解析结果必须是非空 dict",那才会把空文件和全新安装一起打死**——
移交项担心的正是这个形状,**它对,但它只对那个写错的判据**。

**(c) 只查"抛不抛"漏掉一类。** 顶层是列表的 YAML(`- a` / `- b`)解析得干干净净,
守卫放行;可 `read_raw_config` 拿到它之后:

`hermes_cli/config.py:3055 @ 863e313`

```python
        if not isinstance(data, dict):
```

——**强制降级成 `{}`**,于是又回到"读出空 dict 再整文件覆盖"的老路。
**同一个事故,另一个入口。** 所以完整判据必须是「不抛 **且** 结果 `None` 或 `dict`」。
这一条是本段相对移交项问法的**净增量**:移交项只问了"补解析检查会不会破坏语义",
没问"补了解析检查够不够"。

**(d) 代价:未知 YAML 标签会被新拒。** `model: !Custom foo` 现在放行、补检查后
抛 `ConstructorError` 被拒。真实场景是"用新版本 Hermes 写的配置,拿旧版本去改"。
这是一个**真实的行为变更**,不是零成本。取舍上我判它可接受——
拒绝时给的是一句可操作的错误("移开或修好这个文件"),而放行的代价是静默丢配置——
**但它必须写进变更说明,不能当成没有。**

---

## 3. 落点:补在收口里,理由不是"多数派"

R8-fix 的推断是:"五个裸写点里四个各自在收口之外补了检查,说明补在收口里可能才是对的落点。"
**结论对,但这个理由不够。** 四个调用方各自补检查,同样可以解释成"每个调用方的语义不同,
本来就该各补各的"。

**先排除一个会误导修复方向的读法。** 本轮另一段(`notes/r8c-raw-auth-py.md` ◎-2)查出:
`atomic_config_write`(`hermes_cli/config.py:3089`)虽自称"唯一 chokepoint",
但它跑的就是同一道 `require_readable_config_before_write`,
**与 `auth.py:7293` 手写的"守卫 + `atomic_yaml_write`"在能力上等价**。
所以**"把 `auth.py:7329` 改成走收口"这个最直觉的修法,修不掉 ■-R8B-12**——
两条路都不查解析。**必须动的是判据本身**,不是路由。
本节说的"补在收口里",指的是**给收口的判据加解析检查**,不是"把调用方赶进收口"。

更硬的理由是:**收口已经有了做这件事所需要的全部信息,而且已经用它做对了一半。**
守卫拿到 `config_path`,已经据此区分了"不存在"与"存在但打不开"。
"存在、打得开、但解析不了"是同一条谱系上的第三格,**信息需求完全相同**,
不需要调用方传任何新东西进来。

而调用方各自补检查的写法,已经被证明会漏——漏掉的那一个就是
`hermes_cli/auth.py:7329`:

`hermes_cli/auth.py:7329 @ 863e313`

```python
    atomic_yaml_write(config_path, config, sort_keys=False)
```

它前面 36 行调了守卫(`hermes_cli/auth.py:7293`),中间读了原始配置,
**什么检查都没做**就整文件替换——而同一个文件里隔 68 行的孪生函数
(`hermes_cli/auth.py:7397` 之前)有空判。**"每个调用方自己记得"这个方案,
在本仓库已经有一次失败记录。**

**搜索面(负结论要写出来)**:在 `/home/user/hermes-agent` 下对全部 `*.py`
搜 `atomic_yaml_write(`,排除 `./tests/` 与函数定义本身,得 11 个调用点;
逐个看目标路径,写 `config.yaml` 的是 `hermes_cli/auth.py:7329`、`:7397`、
`hermes_cli/config.py:3112`(收口自己)、`:3611`、`:4995`、`:5123`、
`hermes_cli/credential_lifecycle.py:174` 七处,其余四处
(`hermes_cli/skin_cmd.py:79`、`hermes_cli/agent_import.py:161`、`hermes_cli/profile_distribution.py:283`、
`profiles.py:878`)写的是别的 YAML 文件,不在本条范围内。
**本段没有独立复核 R8B 那份"五个裸写点、四个各自 fail-closed"的逐点判定**,
只复核了它点名的 `auth.py:7329` 这一处。

---

## 4. 定案

**H-R8FIX-a 结清(设计判断,非新 ■)。** 回答移交项的原问:

- **补解析检查不破坏「全新安装」**:`hermes_cli/config.py:3072` 已先行 `return`。
- **不破坏「空文件」**:`fast_safe_load("")` 返回 `None` 而不抛;"空文档"是合法 YAML。
  破坏空文件语义的是"结果必须非空 dict"这个**写错了的判据**,不是解析检查本身。
- **判据应写成**「解析不抛 **且** 结果是 `None` 或 `dict`」——只查"抛不抛"会漏掉
  顶层非 dict 的输入,而那类输入会被 `hermes_cli/config.py:3055` 降级成 `{}`,
  重新落回同一个事故。
- **落点在收口**(`hermes_cli/config.py:3065`),因为它已持有全部所需信息;
  "调用方各自补"这个方案在本仓库已有一次失败记录(`hermes_cli/auth.py:7329`)。
- **已知代价**:带未知 YAML 标签的配置会从"放行"变成"拒绝并报错"。

**置信度**:高(判据部分,7 种输入均实跑)。
**未做**:没有真的去改被测仓库验证(项目边界:hermes-agent 只读),
所以"改完之后现有测试是否仍全绿"**没有验证**——这是本条唯一的缺口,见 §5。

---

## 5. 本段未覆盖 / 存疑

| 项 | 锚点 | 一句话现象 |
|---|---|---|
| 补检查后现有测试是否仍全绿,未验证 | `tests/hermes_cli/test_migrate_xai.py:204`(`TestUnreadableExistingConfig`)是全仓唯一直接测这道守卫的用例 | 项目边界禁止改被测仓库,所以只做了"判据在 7 种输入上的行为"的实测,**没有**"改完跑全套"的回归证据;那个唯一的用例本轮实跑**失败**,但根因是容器以 root 运行、`chmod 000` 对 root 无效(CLAUDE.md 已在册的环境限制),不是代码缺陷 |
| R8B「五个裸写点、四个 fail-closed」未逐点复核 | `hermes_cli/config.py:3611`、`:4995`、`:5123`、`hermes_cli/credential_lifecycle.py:174` | 本段只复核了 R8B 点名的 `hermes_cli/auth.py:7329`;另外四处写 `config.yaml` 的裸调点是否真的各自 fail-closed,沿用 R8B 结论**未独立验证** |
