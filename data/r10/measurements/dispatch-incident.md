# R10 派工事故记录:编排器路径下的子代理全部报废

本文件记录 R10 开工阶段一次**基础设施级**失败,以及绕过它的办法。
留档的理由:它改变了本轮的执行方式,也解释了本轮的一部分成本。
(按边界要求,本文件不记录任何会话标识或会话专属路径。)

---

## 1. 现象

第一次派工走的是**工作流编排器**(把九片 + 取证 + 查漏共 12 个子代理编成三个阶段)。
12 个子代理**全部报废**:

```text
agent_count=12  agents_done=0  agents_error=12
subagent_tokens=686202  tool_uses=178  duration_ms=1151738
失败原因(每个都一样):StructuredOutput retry cap (5) exceeded — 5 failed calls with no valid output
```

`agents_done=0`,**零产出**:九份底稿一份都没写出来。

## 2. 根因

「结构化输出重试超限」只是**症状**。读子代理的实际执行记录,真正的根因是
**编排器路径下的子代理连一次工具调用都做不成**。每一次 `Bash` / `Read` 都被权限层打回:

```console
<tool_use_error>The permission handler returned updatedInput for Bash that failed schema validation: Bash failed due to the following issue:
The required parameter `command` is missing
This is a configuration issue in your canUseTool callback, PermissionRequest hook, or permission-prompt tool — updatedInput must satisfy the tool's input schema. The tool input from the model was valid.</tool_use_error>
```

注意最后一句:**"The tool input from the model was valid."** ——
子代理发出的调用是合法的,是**权限回调把参数改写成了不合法的形状**再交回去。
`Read` 同理,报的是 `The required parameter 'file_path' is missing`。

于是每个子代理的处境是:拿到派工书,想读文件清单,读不了;想核基线,核不了;
反复几次之后只能如实上报"我什么都没做成"——而那份如实上报的形状不满足结构化输出的
必填字段(它连 `files_total` 该填几都不知道),于是撞上重试上限,整个编排器崩掉。

**这是一次"失败被归错因"的典型**:栈顶的报错(结构化输出重试超限)指向输出格式,
真正的病在最底下(工具权限层)。**只看栈顶会去改 schema,改多少次都没用。**

## 3. 判定它的范围:不是"子代理不可用",而是"编排器路径不可用"

主线自己的工具调用一直正常。所以问题要么在子代理整体,要么只在编排器那条路径。
用一次最小探针分辨(**这一步是关键**,否则会误判成"本轮不能用子代理"从而白白缩小范围):

派一个普通子代理,只让它跑一条命令并原样回报输出。结果:

```text
11 /home/user/hermes-study/data/r10/slices/A.txt
tool_uses: 1   duration_ms: 10354
```

**成功。** 所以结论是:**普通子代理路径正常,编排器路径的权限回调坏了。**
本轮改用普通子代理逐片派工,九片全部正常执行。

## 4. 代价与教训

| 项 | 读数 |
|---|---|
| 白烧的子代理 token | **686,202** |
| 白烧的墙上时间 | **约 19.2 分钟**(1,151,738 ms) |
| 产出 | **0** |
| 恢复动作 | 一次最小探针(约 10 秒)分辨故障范围,然后换派工路径 |

**三条可复用的教训:**

1. **派工前先花十秒验证派工通道本身。** 本轮是先派了 12 个才发现通道坏了。
   一次一条命令的探针,成本是 10 秒,能省 19 分钟和 68 万 token。
2. **不要用产物形态推断异步任务的状态。** 中途主线看到"12 个 agent 都 started、
   编排器已推进到第三阶段",据此**差一点**得出"前两阶段已完成"的结论 ——
   而实际是 12 个全在失败。CLAUDE.md 早有这条规矩(异步产出的完成判定只以完成信号为准),
   本轮再一次印证:当时磁盘上一份底稿都没有,那才是真信号。
3. **报错栈顶不等于根因。** 见 §2。
