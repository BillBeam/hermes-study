# r11b-92 · 修法倒退的更正 —— ■-R11A-01 的修法以 R9C 实证为准

> 主线亲自取证,不转述子代理。溯源约定:`路径:行号 @ 863e313`,锚点单独成行、置于块前。
> 引用本学习仓库自己的文件时,校验器先在基线里找、找不到再在本仓库找
> (`scripts/verify_citations.py:656`),所以下面对 `notes/` / `reports/` 的锚点同样是被机械校验的。
> 实验脚本只监听 `127.0.0.1`,不出网、不碰基线。

## 0. 一句话

**缺陷判定两轮一致,修法被写回了已被证伪的那一条。**

## 1. 三条记录,和它们之间的冲突

### 1.1 R9C 已经定过案:那条修法不够

`notes/r9c-90-handover-rulings.md:11 @ 863e313`

```
| **H-R9A-a** = **H-R9B-d** | R9A 移交(去向写「R9C 或立即」),R9B 已取证 | **改判:维持 ■,但移交项给的修法不足以修好它**;正确修法已在仓库内,实测有效 |
```

这一行同时说了两件事,都要看:**(a)** H-R9A-a 与 H-R9B-d 是**同一条**;
**(b)** 移交项给的修法(比对配置的 connector host / `self._base_url`)**不足以**修好它。

### 1.2 R11A 把修法重新写成了结论

`notes/r11a-90-handover-rulings.md:70 @ 863e313`

```
而正确的比较值**就在同一个类的构造里**,同一文件里还被用来拼规范 URL:
```

同一句话进了报告的定案节:

`reports/round-11a-ops-and-delivery.md:497 @ 863e313`

```
  正确比较值 `self._base_url` 就在同一个类的构造里。同形态在
```

### 1.3 R11A 不是「知道了但不同意」,是根本没提

搜索面:`notes/r11a-90-handover-rulings.md` 全文(419 行),模式
`302|urllib_security|SafeCredential|重定向`,不排除任何区段。

```verify
grep -c "302\|urllib_security\|SafeCredential\|重定向" notes/r11a-90-handover-rulings.md
```

```text
0
```

**零命中。** R11A 的这条定案是在完全没有触及 R9C 论据的情况下写下的,
所以这不是两轮结论之争,是**一条已定的案被后一轮无意识地写回了旧版本**。

---

## 2. 为什么那条修法不够:要害是**校验发生在错的时刻**

被测代码在发起前挂上 bearer,然后交给裸 `urlopen`:

`gateway/relay/media.py:169-172 @ 863e313`

```python
            headers["Authorization"] = f"Bearer {self._bearer()}"

        def _get() -> Optional[str]:
            req = urllib.request.Request(url, headers=headers)
```

`urllib.request.urlopen` **默认跟随重定向,且把 `Authorization` 原样带到新主机**。
主机校验作用在**发起前**的 URL 上;凭据是在 **302 之后**被带走的。
于是一个主机完全合法的 `{base_url}/relay/media/{id}`,只要对端回一个 302,
bearer 就到了别处——而建议的主机校验对此**判通过**。

仓库自带的正确修法,连类名带 docstring 都是对着这个问题写的:

`hermes_cli/urllib_security.py:31-32 @ 863e313`

```python
class SafeCredentialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Preserve request headers only while redirects stay on one origin."""
```

## 3. 重跑得到的实证(本轮补的,R9C 那次跑不了)

R9C 的实验是对的,但它的 ```` ```verify ```` 块指向一个**占位路径**:

`notes/r9c-90-handover-rulings.md:80 @ 863e313`

```
  /home/user/hermes-venv/bin/python /path/to/redirect_probe2.py
```

脚本从未落库。**R11A 自己的全语料证据扫描已经记下它跑不动**,而没有人把这条线索接上:

`data/r11a/measurements/evidence-full-corpus.txt:481 @ 863e313`

```
      stderr: /home/user/hermes-venv/bin/python: can't open file '/path/to/redirect_probe2.py': [Errno 2] No such file or directory
```

本轮把它补成可重跑的探针 `data/r11b/probes/relay_media_redirect_probe.py`:
两个只监听 `127.0.0.1` 的服务,**合法端的主机与 `base_url` 完全相同**
(故建议的主机校验必然通过),合法端回 302 指向受害端。

```verify
HERMES_DISABLE_LAZY_INSTALLS=1 /home/user/hermes-venv/bin/python \
    data/r11b/probes/relay_media_redirect_probe.py
```

```text
建议修法(主机校验)判定 = True
受害端与 base_url 同源  = False

[甲] 裸 urlopen(现状 + 建议的主机校验)
  受害端收到 Authorization = True
  落盘内容来自受害端       = True

[乙] open_credentialed_url(仓库自带的正确修法)
  受害端收到 Authorization = False
  落盘内容来自受害端       = True

结论:主机校验判通过,凭据仍到达受害端 => 该修法不足以修好本缺陷。
```

*(初版探针把两端的 `Host:` 原样打出来,于是**每次重跑输出都不同**——端口是内核分的。
证据命令关卡当场判 `differing=1`,这是它第一次在本轮抓到主线。改法不是给命令加过滤,
是让探针**只输出布尔量**:要钉的断言本来就是「受害端不是 `base_url` 那一端」和
「它收到了 `Authorization`」,把随机端口写进证据只是把噪音当证据。原始 host 移到
`--verbose` 下。)*

**读法**:主机校验判 `True`(修法认为安全),凭据仍到达受害端(`Authorization = True`)。
换成 `open_credentialed_url` 后,同样跟随了 302(仍拿到受害端的响应体),但**凭据被剥掉**。
**这正是 R9C 的结论,独立复现一次。**

## 4. 更正怎么落(以及为什么这样落)

制度对三类产出的改法不同,本条**只更正记录,不改变任何已定案结论的实质**:

| 产出 | 处置 | 依据 |
|---|---|---|
| `notes/r11a-90-handover-rulings.md` | **就地改正文**,并写明「原判是什么、为什么撤、依据是什么」 | `CLAUDE.md`:`notes/` 属「直接改正文」 |
| `reports/round-11a-ops-and-delivery.md` | **正文不动**,文末加勘误节 | `CLAUDE.md`:报告是某一轮的历史记录 |
| 缺陷本身(■) | **不动**。两轮判定一致:子串判定 + 入站可控 URL = 网关 bearer 外泄 | 这不是被推翻的结论 |

**不立新案号。** R9C 已经定过案(§1.1),本轮做的是把 R11A 写回旧版本的那一句**还原**到
R9C 的定案,不是提出新结论。按边界「若普查发现某条旧结论确应推翻,须作为新定案单独立项」
——本条不属该情形,因为**要推翻的那一版本身就是倒退**,正确版早已在册。

## 5. 这条为什么会发生(供 §其一 的合并规则参考)

`■-R11A-01` 的立项路径是 **H-R9B-d 升格**。而 H-R9B-d 在 R9C 已被并入 H-R9A-a 并一起定案
(§1.1)。R11A 拿到的移交表来自 R10B:

`notes/r10b-90-handover-rulings.md:345 @ 863e313`

```
| H-R9B-d | R11A | `gateway/relay/media.py:94` 的 `is_relay_media_url` —— 复核:解析得到,行号正确 |
```

这一行复核的是**锚点解析得到、行号正确**——都对。它没有(也没被要求)去查
**这条移交项是否已在别处结过案**。于是一条已定案的条目以「未决移交」的身份继续流转,
**两轮之后连它的定案内容一起被覆盖**。

**给合并规则的输入**:去重不能只按案号,因为这里三个案号(H-R9A-a / H-R9B-d / ■-R11A-01)
指同一处代码;也不能只按锚点行号,因为它们分别锚在 `:92`(函数头)与 `:94`(那句 `in`)。

## 移交

| 移交项 | 去向 | 锚点 | 现象 |
|---|---|---|---|
| **H-R11B-a** | 接手网关中继的那一轮 | `gateway/relay/adapter.py:471`:`if "/relay/media/" not in url:` | ■-R11A-01 的同形态子串判定在非测试代码里另有 2 处(`:471` 与 `:477`,后者是 `elif "/relay/media/" not in url:`),本轮只更正修法记录、未逐处取证它们是否也带凭据 |
