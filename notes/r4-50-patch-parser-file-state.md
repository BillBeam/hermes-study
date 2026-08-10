# R4-50 V4A 补丁解析 + 跨代理文件新鲜度守卫

> 底稿。基线 `863e31318`。范围:`tools/patch_parser.py`(729)、`tools/file_state.py`(332)。
> 这两个是"文件工具"的支撑件,R4 卡片点名 patch_parser;file_state 与并发环境强相关,一并覆盖。

## 1. V4A 补丁格式解析(patch_parser.py)

**问题**:模型要改一个文件,怎么表达"改哪几行"?一种通用格式是 V4A(codex、cline 等编码 agent 共用),
一份补丁可以在一次调用里做多个操作:更新文件、新建文件、删文件、移动文件。harness 要把这个文本格式解析成
结构化操作再落地。

**格式**(tools/patch_parser.py:8-24 docstring):
```
    *** Begin Patch
    *** Update File: path/to/file.py
    @@ optional context hint @@
     context line (space prefix)
    -removed line (minus prefix)
    +added line (plus prefix)
    *** Add File: path/to/new.py
...
    *** Delete File: path/to/old.py
    *** Move File: old/path.py -> new/path.py
    *** End Patch
```

**机制**:两阶段。
- `parse_v4a_patch(patch_content)`(tools/patch_parser.py:70)→ `(operations, error)`:把文本解析成
  `PatchOperation` 列表(每个带 OperationType + Hunk 列表)。解析失败返回错误串而非抛异常。
- `apply_v4a_operations(operations, file_ops)`(tools/patch_parser.py:394):通过一个 `file_ops` 接口落地每个操作。
  V4A **绕过** WriteResult/PatchResult 常规管线(tools/patch_parser.py:430 注释),但仍尽力回传 LSP 诊断和 lint
  结果(`_apply_add` 从 WriteResult 抽 `lsp_diagnostics` 和 `lint`,tools/patch_parser.py:539-546),让补丁也能
  surface 语法检查。

**上下文匹配**:hunk 的上下文行(空格前缀)用来在文件里定位改动位置。这里和 R3 的 `fuzzy_match` 联动——
V4A 补丁的模糊匹配走那 9 策略链(R3-20 §5),`patch` 工具的 `old_string` 定位就是 fuzzy_match。
patch_parser 负责**解析格式**,fuzzy_match 负责**容错定位**。

**取舍**:V4A 是多编码 agent 的事实标准,支持它让 hermes 能吃 codex/cline 风格的补丁;绕过常规写管线是
为了一次补丁多操作的原子性,代价是要单独把 LSP/lint 结果接回来。

## 2. 跨代理文件新鲜度守卫(file_state.py)

**问题(一次并发故障走法)**:两个子代理在同一进程、同一文件系统上并发干活。子代理 A 读了 `config.py`,
子代理 B 随后改了 `config.py`,然后 A 拿着**读到的旧内容**去写 `config.py`——把 B 的改动覆盖掉了。R2 的
分段调度器(tool_dispatch_helpers 的路径重叠检查)只管**单个 agent 内**一批工具的路径冲突,管不了
**跨子代理**的这种读后写竞态。

**机制**:一个进程级单例 `FileStateRegistry`(tools/file_state.py:59)按解析后的路径跟踪三样东西:
- 每 agent 的读时间戳:`{task_id: {path: (mtime, read_ts, partial)}}`;
- 全局最后写者:`{path: (task_id, write_ts)}`;
- 每路径一个 `threading.Lock`,包住 read→modify→write 临界区。

三个公共钩子给文件工具用(tools/file_state.py:19-22):
- `record_read(task_id, path, partial)` —— read_file 调用后记读时间戳;
- `note_write(task_id, path)` —— write_file/patch 后记写者;
- `check_stale(task_id, path)` —— write_file/patch **前**检查:如果本 agent 上次读之后有别人写过这个文件,
  返回警告(说明内容可能已过期,让 agent 重读再写)。

`tools/file_state.py:142 @ 863e313`:
```python
    def check_stale(self, task_id: str, resolved: str) -> Optional[str]:
```
外加 `lock_path(path)` 上下文管理器包住整个读改写块,`writes_since(task_id, since_ts, paths)` 给
delegate_tool 的"子代理完成提醒"用(看子代理干活期间改了哪些文件)。

**与单代理机制的分工**(tools/file_state.py:1-31 docstring):它刻意独立于 `file_tools.py` 的 `_read_tracker`
(那个是 per-task、处理连续读);也补充 `run_agent._should_parallelize_tool_batch` 的单代理路径重叠检查
(R2 分段调度)。三者各管一层:分段调度管单 agent 一批工具、_read_tracker 管 per-task 连续读、
FileStateRegistry 管跨子代理的读后写。

**逃生阀**:`HERMES_DISABLE_FILE_STATE_GUARD=1` 时所有方法 no-op(tools/file_state.py:25)。

**取舍**:进程级单例只能守"同进程"的子代理(gateway 里并发子代理是同进程),跨进程(不同 Hermes)的并发
写它守不住——但那种情况罕见,且有环境层(docker persist)的容器隔离兜底。

## 3. 重实现要点

1. 多操作补丁格式(更新/新建/删/移)解析与落地两阶段分离;绕过常规写管线时要把诊断/lint 结果单独接回。
2. 补丁定位交给专门的模糊匹配层(容错),解析器只管格式。
3. 跨并发单元的"读后写覆盖"要用进程级注册表:记读时间戳 + 全局最后写者,写前检查新鲜度,配每路径锁包住
   读改写临界区。这层独立于"单执行流内的路径冲突"检查。

## 4. 延伸

环境抽象 r4-01;docker/terminal/process r4-02;远端后端与 serverless r4-20(子代理);浏览器 r4-30;
computer_use r4-40。
