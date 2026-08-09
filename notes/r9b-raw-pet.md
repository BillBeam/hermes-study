# R9B 底稿 · 虚拟宠物 pet(`agent/pet/**`,11 文件 / 3,653 行)

> 溯源约定:凡对 hermes-agent 行为的断言,锚点 `路径:行号 @ 863e313` 单独成行、置于代码块之前,
> 块内为基线逐字摘录。基线只读,收工时 `git status --porcelain` 为空。
> 术语锚定:**sprite(精灵)** = 一张小尺寸角色画;**spritesheet / atlas(精灵表 / 图集)** =
> 把许多帧按固定网格拼进一张大图;**chroma key(色键)** = 用一种纯色当背景、事后按颜色抠掉;
> **kitty graphics protocol** = 终端里直接画真彩位图的转义序列协议;
> **half-block(半块)** = 用 `▀` 这个上半块字符 + 前景/背景两种颜色,让一个终端字符格表达两个像素。

---

## 0. 本簇范围与文件清单

| 文件 | 行数 | 一句话职责 |
|---|---:|---|
| `agent/pet/__init__.py` | 51 | 包门面 + 全簇定位声明 |
| `agent/pet/constants.py` | 167 | 帧几何、`PetState` 枚举、两套行分类法与别名解析 |
| `agent/pet/manifest.py` | 165 | 拉取 petdex 公共目录(只读、无凭据、进程内 TTL 缓存) |
| `agent/pet/render.py` | 682 | 解码精灵表 + 四种终端协议编码(kitty / iTerm2 / sixel / 半块) |
| `agent/pet/state.py` | 81 | **活动 → 动画行** 的纯函数(全簇唯一的"语义"文件) |
| `agent/pet/store.py` | 503 | 磁盘存储:安装 / 枚举 / 解析 / 导出 / 改名 / 缩略图 |
| `agent/pet/generate/__init__.py` | 29 | 生成子包门面 |
| `agent/pet/generate/atlas.py` | 1183 | **确定性**图像处理:抠背景 → 切帧 → 配准 → 拼图集 → 校验 |
| `agent/pet/generate/imagegen.py` | 251 | 图像后端解析 + N 变体循环 + 参考图接地 |
| `agent/pet/generate/orchestrate.py` | 358 | 两步编排:base 草稿 → hatch(孵化) |
| `agent/pet/generate/prompts.py` | 183 | 两种形状的提示词构造器 |
| 合计 | **3,653** | |

**结构上的第一个观察:这 3,653 行不是一件东西,是两件。**
运行时展示侧 = `__init__ + constants + manifest + render + state + store` = **1,649 行**;
一次性资产生产侧 = `generate/*` = **2,004 行(54.9%)**。
后者只在 `/hatch` 时执行一次,产物落盘后再不参与任何渲染路径。
把它们当一件事读,是读不懂这个簇的。

---

## 1. 它到底是什么、被谁调用、默认开不开

### 1.1 总问题的答案

**运行时那 1,649 行是"状态可视化载体";生成侧那 2,004 行是"资产工厂"。玩具成分有,
留存机制(engagement)成分几乎为零 —— 因为它没有任何随时间演进的宠物状态。**

三条硬证据。

**(a) 作者自己把定位写进了包 docstring,而且这句话是可验证的。**

`agent/pet/__init__.py:27 @ 863e313`
```
The whole feature is a *display* concern: it adds no model tool, mutates no
system prompt or toolset, and therefore has zero effect on prompt caching.
"""
```

我按下面的搜索面独立复核了这句里最强的那半句("adds no model tool"):

```verify
cd /home/user/hermes-agent
# 面 1:全仓 Python 里有没有名字含 pet 的工具 schema(工具定义统一是 {"name": "<tool>"})
grep -rniE '"name"[[:space:]]*:[[:space:]]*"[a-z_]*pet[a-z_]*"' --include="*.py" . | wc -l
# 面 2:系统提示词 / 工具分发 / 工具执行 三个必经文件里有没有 pet 这个词
grep -rniE "\bpet\b" agent/prompt_builder.py agent/tool_dispatch_helpers.py \
    agent/tool_executor.py tools/__init__.py | wc -l
```

两条都是 `0`。**排除项**:本搜索面不覆盖 `skills/` 下的技能文档
(`skills/autonomous-ai-agents/hermes-agent/references/petdex.md` 确实教模型去 **跑 `hermes pets` 命令**),
所以精确的说法是:**pet 没有专属模型工具,但模型可以经由通用 `terminal` 工具 + 技能文档间接操作它。**
这不与 docstring 矛盾 —— 它说的是"不新增工具"。

**(b) 状态从哪来 —— 从 agent 的活动信号来,不是从时间来。**

`agent/pet/state.py:67 @ 863e313`
```
    if error:
        return PetState.FAILED
    if celebrate:
        return PetState.JUMP
    if just_completed:
        return PetState.WAVE
    if awaiting_input:
        return PetState.WAITING
    if tool_running:
        return PetState.RUN
    if reasoning:
        return PetState.REVIEW
    if busy:
        return PetState.RUN
    return PetState.IDLE
```

这是全簇唯一的语义函数,**无状态、纯函数、7 个布尔入参 → 1 个枚举出参**。
没有 `self`,没有持久化,没有时间。它就是一个 status indicator 的映射表。

**(c) 全簇没有饥饿 / 心情 / 等级 / 进化 —— 负结论,附搜索面。**

```verify
cd /home/user/hermes-agent
grep -rniE "hunger|hungry|\bmood\b|happiness|\blevel\b|\bxp\b|evolve|evolution|lifespan" \
    agent/pet/ --include="*.py"
```

实际输出:

```text
agent/pet/constants.py:68:    readable rather than letting it devolve into a blob.
agent/pet/generate/atlas.py:137:    thick dark outline keeps the silhouette intact. Built on a C-level filter, no
agent/pet/generate/atlas.py:175:    # hot magenta): remove all near-key opaque pixels with C-level channel ops.
agent/pet/generate/atlas.py:226:    # One C-level composite instead of millions of per-pixel writes: paint the
agent/pet/generate/prompts.py:127:        "Honor the requested tone and mood exactly (cute, eerie, scary, menacing, whimsical, etc.) "
agent/pet/generate/prompts.py:152:        "preserving the same emotional tone/mood (e.g., scary stays scary, cute stays cute), "
```

6 条命中**全部是散文**(`devolve`、`C-level`、提示词里的 `tone and mood`),
没有一条是状态字段。**排除项**:只搜了 `agent/pet/**.py`,
未搜 TypeScript 桌面端(`apps/desktop/src/store/pet.ts` 有 roam 漫游状态,那是窗口内位置动画,
不是养成数值)。结论限定在 Python 侧:**没有任何随时间演进的宠物属性,
所以它不是电子宠物(Tamagotchi),是一个会做表情的状态灯。**

### 1.2 被谁调用

```verify
cd /home/user/hermes-agent
grep -rn "agent\.pet" --include="*.py" . | grep -v "^./agent/pet/" | grep -v "^./tests/" \
    | cut -d: -f1 | sort | uniq -c | sort -rn
```

```text
     17 ./tui_gateway/methods_session.py
     17 ./hermes_cli/pets.py
      7 ./tui_gateway/server.py
      6 ./cli.py
      5 ./hermes_cli/cli_commands_mixin.py
```

**生产代码只有 5 个调用方**,分三条线:

1. **基础 CLI 内嵌面板** —— `cli.py`。pet 是 prompt_toolkit 的一个 `Window`,
   放在输入提示上方,高度为 0 时整个折叠(未启用的人零感知)。
   `cli.py:16642 @ 863e313`
   ```
        self._pet_widget = Window(
            content=FormattedTextControl(self._pet_fragments),
            height=self._pet_widget_height,
            align=WindowAlign.RIGHT,
        )
   ```
   动画由一个 daemon 线程驱动,每 0.16s 推一帧、每 2.5s 重读一次配置(所以 `/pet` 改配置不用重启):
   `cli.py:5797 @ 863e313`
   ```
    def _pet_anim_loop(self) -> None:
        """Advance the frame + invalidate on a timer while a pet is enabled."""
        while self._pet_anim_running:
            time.sleep(self._PET_FRAME_INTERVAL)
            now = time.monotonic()
            if now - self._pet_cfg_checked >= self._PET_CFG_INTERVAL:
                self._pet_cfg_checked = now
                self._pet_resolve_config()
            if not self._pet_enabled:
                continue
   ```

2. **命令行子命令与斜杠命令** —— `hermes_cli/pets.py`(`hermes pets ...`)、
   `hermes_cli/cli_commands_mixin.py`(`/pet`、`/hatch`)。

3. **网关 RPC(TUI + Electron 桌面)** —— `tui_gateway/methods_session.py` 里 16 个
   `pet.*` 方法(`pet.info` / `pet.info.meta` / `pet.cells` / `pet.gallery` / `pet.select` /
   `pet.remove` / `pet.export` / `pet.rename` / `pet.thumb` / `pet.disable` / `pet.scale` /
   `pet.cancel` / `pet.generate.status` / `pet.generate` / …)。
   TUI 侧不能画布,所以网关把精灵**降采样成半块单元格数组**发过去,Ink 用原生颜色属性画:
   `tui_gateway/methods_session.py:1378 @ 863e313`
   ```
    """Return half-block cell frames for one pet state (TUI renderer).

    The TUI can't draw a canvas, so the engine downsamples the spritesheet to
    a grid of half-block cells and the Ink side paints them with native color
    props. Each cell is ``[tr,tg,tb,ta, br,bg,bb,ba]`` (top + bottom pixel).
   ```

### 1.3 与全仓的耦合面:**5 个 import 语句**

```verify
cd /home/user/hermes-agent
grep -rnE "^[[:space:]]*(from|import) " --include="*.py" agent/pet/ \
  | grep -vE "from __future__|from agent\.pet" \
  | grep -E "from (agent|hermes|tools|gateway|tui_gateway|plugins|cli)"
```

```text
agent/pet/generate/imagegen.py:66:        from hermes_cli.plugins import _ensure_plugins_discovered
agent/pet/generate/imagegen.py:83:    from agent.image_gen_registry import get_active_provider, get_provider
agent/pet/generate/imagegen.py:139:    from agent.image_gen_registry import get_provider
agent/pet/generate/imagegen.py:164:        from agent.image_gen_provider import save_url_image
agent/pet/store.py:25:from hermes_constants import get_hermes_home
```

3,653 行只经由 **4 个模块、5 个 import 点**接触仓库其余部分,而且其中 4 个还都在 `generate/` 里。
**运行时那一半(render / state / store / constants / manifest)对全仓的依赖只有一个
`hermes_constants.get_hermes_home`。** 这是本簇最值得抄走的工程性质:
一个可以整包删掉而不伤主干的功能簇。

### 1.4 默认开不开:**关**

`hermes_cli/config_defaults.py:1286 @ 863e313`
```
        "pet": {
            "enabled": False,
            # Active pet slug; resolved against installed pets in
            # get_hermes_home()/pets/. Empty → first installed pet.
            "slug": "",
            # Terminal render protocol for CLI/TUI:
            #   auto  — detect kitty/iTerm2/sixel, else unicode half-blocks
            #   kitty | iterm | sixel | unicode | off
            "render_mode": "auto",
            # Master size scalar (relative to native 192×208 frames). One knob
            # shrinks every surface: the desktop canvas scales its pixels by it
            # and the CLI/TUI derive their terminal column width from it. The
            # half-block fallback clamps to a legibility floor (it can't shrink
            # as far as true-pixel kitty/GUI without turning to mush).
            "scale": 0.33,
            # Hard override for terminal column width. 0 = auto (derive from
            # scale); set a positive int only to pin the half-block/kitty width
            # independently of scale.
            "unicode_cols": 0,
        },
```

且**三重关闭**:`enabled=False` + 没装宠物时 `resolve_active_pet` 返回 `None` +
非 TTY 时 `resolve_mode` 直接返回 `"off"`。任何一层不满足都渲染不出来。

---

## 2. `generate/atlas.py` 结构测绘(1,183 行)

### 2.1 atlas 是什么、为什么需要它

**atlas / spritesheet = 一张大图,按固定网格切成 N 个等大格子,每格一帧动画。**
这里的契约是 **行 = 状态,列 = 该状态的第几帧**。

`agent/pet/generate/atlas.py:43 @ 863e313`
```
ROW_SPECS: list[tuple[str, int, int]] = [
    ("idle", 0, 6),
    ("running-right", 1, 8),
    ("running-left", 2, 8),
    ("waving", 3, 4),
    ("jumping", 4, 5),
    ("failed", 5, 8),
    ("waiting", 6, 6),
    ("running", 7, 6),
    ("review", 8, 6),
]
```

`agent/pet/generate/atlas.py:55 @ 863e313`
```
ROWS = len(ROW_SPECS)
COLUMNS = max(count for _, _, count in ROW_SPECS)
ATLAS_WIDTH = COLUMNS * CELL_WIDTH
ATLAS_HEIGHT = ROWS * CELL_HEIGHT

FRAME_COUNTS: dict[str, int] = {state: count for state, _, count in ROW_SPECS}
```

即 `COLUMNS = 8`、`ROWS = 9`、单元格 `192×208`(来自 `constants.FRAME_W/FRAME_H`),
整图 **1536×1872**。

**为什么需要它(三个理由,按重要性排):**

1. **一次解码,O(1) 取帧。** 渲染端只要 `Image.open` 一次,之后取任何帧都是纯 `crop`
   坐标算术。若一帧一文件,60 帧就是 60 次文件 IO + 60 次解码。
2. **单文件即"一只宠物"。** 分发单位 = `pet.json + spritesheet.webp` 两个文件,
   下载/打包/导出都是原子的(见 `store.export_pet`)。
3. **格式即互操作契约。** 它刻意对齐 petdex/Codex 的公开标准,所以本地生成的宠物
   可以反向提交回公共图库。作者在文件头把这点写死了:
   `agent/pet/generate/atlas.py:9 @ 863e313`
   ```
The atlas follows the **petdex/Codex standard**: 8 columns x 9 rows of
``192x208`` cells (``1536x1872``), with the row order + per-row frame counts
from OpenAI's ``hatch-pet`` skill. Our renderer (:mod:`agent.pet.render`) keys
frames as ``rows = states, cols = frames`` via
:data:`agent.pet.constants.CODEX_STATE_ROWS`, and a pet built here is a valid
``petdex submit`` spritesheet. Rows shorter than 8 columns leave the trailing
cells fully transparent.
   ```

### 2.2 结构测绘:五段流水线

文件用 `# ─────` 横幅分成 3 个显式段,实际是 5 个处理阶段。全部函数如下(锚点+摘录逐条可查):

| 阶段 | 函数(锚点:摘录) | 作用 |
|---|---|---|
| ① 抠背景 | `agent/pet/generate/atlas.py:78`:`def _color_distance(r: int, g: int, b: int, key: tuple[int, int, int]) -> float:` | RGB 欧氏距离 |
| | `agent/pet/generate/atlas.py:82`:`def _has_transparency(image) -> bool:` | 判断已带真 alpha 就别抠了 |
| | `agent/pet/generate/atlas.py:94`:`def _dominant_corner_color(image) -> tuple[int, int, int]:` | 四角采样猜背景色 |
| | `agent/pet/generate/atlas.py:110`:`def _near_key_mask(image, key: tuple[int, int, int], tol: int = 48):` | C 级通道点运算生成掩码 |
| | `agent/pet/generate/atlas.py:130`:`def _defringe(rgba):` | 3×3 最小值滤波削掉 1px 抗锯齿彩边 |
| | `agent/pet/generate/atlas.py:146`:`def remove_background(image, *, chroma_key: tuple[int, int, int]` | 主入口:边界洪泛填充 |
| | `agent/pet/generate/atlas.py:232`:`def _repair_internal_alpha_holes(image):` | 补"瑞士奶酪"式内部透明洞 |
| ② 切帧 | `agent/pet/generate/atlas.py:323`:`def _fit_to_cell(image):` | 裁内容→缩放→居中进 192×208 |
| | `agent/pet/generate/atlas.py:352`:`def _drop_side_bleed(image):` | 丢掉邻格渗进来的小侧瓣 |
| | `agent/pet/generate/atlas.py:389`:`def _erase_long_axis_lines(image):` | 擦掉模型画的地平线/分栏线 |
| | `agent/pet/generate/atlas.py:440`:`def _component_boxes(image) -> list[tuple[tuple[int, int, int, int], int]]:` | 连通域标记(手写 BFS) |
| | `agent/pet/generate/atlas.py:488`:`def _isolate_slot_subject(image):` | 保主体、丢闪光/眼泪 |
| | `agent/pet/generate/atlas.py:520`:`def _has_slot_padding(image) -> bool:` | 四边留白检查 |
| | `agent/pet/generate/atlas.py:532`:`def _slot_bounds(width: int, frame_count: int) -> list[tuple[int, int]]:` | 等分槽位 |
| | `agent/pet/generate/atlas.py:539`:`def _group_component_rows(boxes: list[tuple[int, int, int, int]]) -> list[list[tuple[int, int, int, int]]]:` | 按视觉行分组 |
| | `agent/pet/generate/atlas.py:563`:`def _merge_related_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:` | 合并披风/尾巴等断开部件 |
| | `agent/pet/generate/atlas.py:599`:`def _component_crops(strip, frame_count: int, *, require_padding: bool = False) -> list` | 严格路径:按连通域切 |
| | `agent/pet/generate/atlas.py:662`:`def _sever_expected_gutters(strip, frame_count: int):` | 在预期边界切一刀细缝 |
| | `agent/pet/generate/atlas.py:690`:`def _slot_crops(strip, frame_count: int, *, require_padding: bool = False) -> list` | 兜底:等宽切 |
| | `agent/pet/generate/atlas.py:709`:`def _content_runs(profile: list[int], *, threshold: int = 2) -> list[tuple[int, int]]:` | 列投影找空隙 |
| | `agent/pet/generate/atlas.py:727`:`def _frame_x_ranges(strip, frame_count: int) -> list[tuple[int, int]]` | 由空隙推每帧 x 区间 |
| | `agent/pet/generate/atlas.py:764`:`def _significant_subject_boxes(image) -> list[tuple[int, int, int, int]]:` | 显著主体框 |
| | `agent/pet/generate/atlas.py:772`:`def _validate_extracted_frames(frames: list, frame_count: int) -> None:` | 拒收"一帧里塞了多个姿势" |
| | `agent/pet/generate/atlas.py:810`:`def extract_strip_frames(` | **公开入口** |
| ③ 配准 | `agent/pet/generate/atlas.py:880`:`def _column_profile(image) -> list[int]:` | 把帧压成 1px 高的列剖面 |
| | `agent/pet/generate/atlas.py:887`:`def _best_shift(ref: list[int], prof: list[int], window: int) -> int:` | 1-D 相位相关求最佳位移 |
| | `agent/pet/generate/atlas.py:908`:`def normalize_cells(frames_by_state: dict[str, list], *, pad: int = _NORMALIZE_PAD) -> dict[str, list]:` | **反抖动核心** |
| ④ 拼图 | `agent/pet/generate/atlas.py:1010`:`def single_frame(image, *, fit: bool = True):` | 单图→一帧(idle 兜底) |
| | `agent/pet/generate/atlas.py:1026`:`def _clear_transparent_rgb(image):` | 全透明像素的 RGB 清零 |
| | `agent/pet/generate/atlas.py:1038`:`def mirror_frames(frames: list) -> list:` | 逐帧水平镜像 |
| | `agent/pet/generate/atlas.py:1052`:`def compose_atlas(frames_by_state: dict[str, list]):` | 按 ROW_SPECS 打包 |
| | `agent/pet/generate/atlas.py:1071`:`def atlas_to_webp_bytes(atlas) -> bytes:` | 无损 WebP 编码 |
| ⑤ 校验 | `agent/pet/generate/atlas.py:1078`:`def validate_atlas(atlas) -> dict:` | 几何/占格/透明度不变量 |

### 2.3 三个"为什么这么设计"

**(a) 模型永远不拥有网格几何。** 这是整份文件的立论:

`agent/pet/generate/atlas.py:3 @ 863e313`
```
Image-generation models are good at *drawing* a row of poses but bad at exact
grid geometry, so the model never owns the atlas layout: it produces one loose
horizontal strip per state, and these deterministic ops slice that strip into
clean, centered, transparent ``192x208`` cells and pack them into the sheet our
renderer reads.
```

取舍:**换来可测试性**(整条 `generate/` 流水线可以完全离线跑,`tests/agent/test_pet_generate.py`
用合成条带跑通了 compose→validate→register→adopt),**代价是 1,183 行手写图像处理**,
而且每一条启发式规则都是对某个具体翻车样本的补丁(Frogger 侧瓣、Gemini 画地平线、
"postage stamp" 缩成邮票……)。

**(b) 抠背景用"边界洪泛"而不是"全局颜色匹配"。**

`agent/pet/generate/atlas.py:147 @ 863e313`
```
    """Return *image* (RGBA) with its flat background keyed out to transparent.

    If the strip already has a transparent background we leave it alone; else we
    key out *chroma_key* (or the dominant corner color when not given) via a
    **border flood-fill**: only background-coloured pixels *connected to an edge*
    are removed. A global color match (the old approach) punched holes in the pet
    wherever an interior highlight happened to match the backdrop — e.g. a pug's
    light belly against a near-white background — which then showed through as the
    window behind. Flood-fill keeps those interior pixels because they aren't
    reachable from the border without crossing the (non-background) pet.
    """
```

这是一条**教科书式的因果记录**:全局匹配 → 哈巴狗浅色肚皮被打洞 → 改边界洪泛。
但边界洪泛又漏掉"被四肢围住的口袋",于是**只在饱和色键(我们自己的洋红背景)下**
额外从内部近色像素播种 —— 因为对着一个灰白色键这么干,正是它要防的打洞。
纯 Python 逐像素洪泛在 ~150 万像素上会打满一个核,所以先走 C 级通道运算的快路径:
`agent/pet/generate/atlas.py:186 @ 863e313`
```
    # Mark removals in a flat mask and apply them in one C composite at the end —
    # writing `px[x, y] = (0,0,0,0)` per pixel was ~3M PixelAccess calls (84% of
    # the whole pipeline) and pegged a core in pure Python, stalling the gateway.
```

**(c) 反抖动用相位相关,而不是"每帧裁剪居中"。**

`agent/pet/generate/atlas.py:909 @ 863e313`
```
    """Register every frame into a 192x208 cell — the deterministic anti-jitter math.

    A per-frame "crop→scale→center" pipeline jitters because a moving limb/cape
    shifts the bbox (or even the centroid) and a per-frame scale pulses the size.
    The rigorous fix, matching image-registration practice (phase correlation)
    and AI-sprite pipelines (perfectpixel-studio / sprite-gen):

    1. **Cross-correlate** each frame's column profile against the per-state
       *median* profile to find the integer shift that locks the **body** in
       place — robust to limbs/cape because the body dominates the profile.
    2. **Union-crop** through one shared state window, then scale every state by a
       single global factor keyed to its median pose height, so the character is
       the same on-screen size in every row while a jump's lift still fits.
    """
```

关键取舍在第 2 步的全局 K:一个"跳跃"行的运动包络天生更高,若各行独立缩放,
跳跃行的宠物就会比 idle 行小一圈。作者的解法是**用中位姿势高度定尺度、用并集框定上限**,
一个 K 管全部状态。行为规格见 §7 表里的
`test_normalize_cells_uses_consistent_pose_scale_for_motion_rows`,断言 idle 与 jumping
的成品高度差 ≤8px。

**(d) 校验是"视觉有效性"而非"非空"。** 三档:整图尺寸 → 全局中位帧高 ≥ `max(56, 0.28*208)`
→ 每状态相对全局中位的塌缩守卫:
`agent/pet/generate/atlas.py:1160 @ 863e313`
```
            min_state_w = max(32, round(global_med_w * 0.42))
            min_state_h = max(40, round(global_med_h * 0.50))
            if med_w < min_state_w or med_h < min_state_h:
                errors.append(
                    f"state '{state}' appears collapsed (median {med_w}x{med_h}px, global median {global_med_w}x{global_med_h}px)"
                )
```
理由写在注释里:一行坏行会毒化全局归一化,把**整只宠物**缩成邮票,而旧的"格子非空"检查
对此完全无感。

---

## 3. 生成管线(重点:与图像生成簇是复用还是另起一套)

### 3.1 结论:**provider 层复用,工具层另起一套**

- **复用的**:`agent.image_gen_registry.get_active_provider / get_provider`(后端注册表)、
  `agent.image_gen_provider.save_url_image`(URL→本地落盘)、
  `hermes_cli.plugins._ensure_plugins_discovered`(插件发现)。
  即**同一套 provider 抽象、同一份用户凭据、同一批插件后端**。
- **另起的**:不经过 `tools/image_generation_tool.py`(那是模型可见的 `image_generate` 工具)。
  搜索面见 1.3 的 `verify` 块 —— `agent/pet/**` 里对 `tools/` 的 import 数为 0。

**为什么另起。** 三件事 agent 面工具给不了:

**(a) N 变体 + "透明背景"能力探测回退。** 工具层一次一张;精灵生成要一次出 4 张 base 草稿,
而且不同模型对 `background=transparent` 的支持不一,得探测一次、失败就对**剩余全部变体**
关掉这个 flag:
`agent/pet/generate/imagegen.py:236 @ 863e313`
```
    allow_transparent = True
    for _ in range(max(1, n)):
        path, err = _run({"background": "transparent"} if allow_transparent else {})
        # Model doesn't support the transparent flag → drop it for this and every
        # remaining variant (no point re-probing a capability we just disproved).
        if path is None and allow_transparent and _rejected_background(err):
            allow_transparent = False
            path, err = _run({})
        if path is not None:
            out.append(path)
        else:
            last_error = err
```
行为规格见 §7 表里的
`test_generate_retries_without_transparent_background`,断言三次调用的 background 参数序列
恰为 `["transparent", None, None]`。

**(b) 参考图 kwarg 名在后端间不统一,这里两个名字都发。**
`agent/pet/generate/imagegen.py:211 @ 863e313`
```
    def _run(extra: dict) -> tuple[Path | None, str]:
        kwargs: dict = {"aspect_ratio": aspect_ratio, **extra}
        if refs:
            # Providers disagree on the ref kwarg name: our OpenRouter/Nous
            # backends read ``reference_images``, OpenAI's gpt-image-2 reads
            # ``reference_image_urls``. Send both; each ignores the other.
            kwargs["reference_images"] = refs
            kwargs["reference_image_urls"] = refs
```

**(c) "必须支持参考图"这条硬门槛 + 自己的偏好序。**
`agent/pet/generate/imagegen.py:23 @ 863e313`
```
# Providers that can ground generation on a reference image, in preference order
# (Nous Portal → OpenAI → OpenRouter → …). OpenRouter/Nous run a quality-first
# model chain and may fall back depending on account access and endpoint behavior,
# so fidelity can vary by configured backend + model availability.
_REF_CAPABLE = ("nous", "openai", "openai-codex", "openrouter", "krea")

# Friendly display label per reference-capable provider, surfaced in the desktop
# pet-gen picker.
_PROVIDER_LABELS: dict[str, str] = {
    "nous": "Nous Portal",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "openai-codex": "OpenAI (Codex)",
    "krea": "Krea",
}
```
解析顺序:`HERMES_PET_IMAGE_PROVIDER` 强制 → 调用方 `prefer` → 全局 active(若在白名单内)
→ 白名单里第一个可用的 → 抛 `GenerationError` 并给可执行的修复提示。
**设计取舍**:宁可硬失败并指路,也不"静默产出一只每行都长得不一样的宠物":

`agent/pet/generate/imagegen.py:10 @ 863e313`
```
Reference grounding only works on providers that support it — currently OpenAI
``gpt-image-2`` (image edits) and Krea (style references). We resolve to one of
those and surface a clear, actionable error otherwise rather than silently
producing an ungrounded, drifting pet.
"""
```

### 3.2 `orchestrate.py` 编排什么

两步,理由是**成本边界**:

`agent/pet/generate/orchestrate.py:36 @ 863e313`
```
# don't hammer the provider's rate limit (one cold call can still be slow).
_MAX_PARALLEL_GENERATIONS = 4
# How many times to (re)generate a single row before accepting a best-effort
# slice. Early attempts demand clean per-pose gutters; the last is lenient so a
# stubborn row still yields frames instead of dropping out entirely.
_ROW_GEN_ATTEMPTS = 3
_MIN_FILLED_STATES = 6
_REQUIRED_STATES = frozenset({"idle", "running-right", "waving"})
```

编排的六件事:

1. **并发扇出**(4 路)。整只宠物是 8 次行生成,串行必然打爆客户端 RPC 超时。
2. **每行三次尝试,前两次严格、最后一次宽松。**
   `agent/pet/generate/orchestrate.py:245 @ 863e313`
   ```
        for attempt in range(_ROW_GEN_ATTEMPTS):
            if cancelled():
                return state, None
            strict = attempt < _ROW_GEN_ATTEMPTS - 1
            try:
   ```
   `strict` → `method="components"`(要求姿势之间有干净空隙,不满足就抛异常重来);
   最后一次 → `method="auto"`(等分槽位兜底,永不抛)。
3. **`running-left` 由 `running-right` 逐帧镜像派生,不生成。**
   `agent/pet/generate/orchestrate.py:283 @ 863e313`
   ```
    # running-left is derived by mirroring running-right (guaranteed-consistent
    # and one fewer generation), so we don't generate it directly.
    generated_specs = [spec for spec in atlas.ROW_SPECS if spec[0] != "running-left"]

    workers = max(1, min(len(generated_specs), _MAX_PARALLEL_GENERATIONS))
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_gen_row, spec) for spec in generated_specs]
        # as_completed runs on the caller (request) thread, so progress events
   ```
   注意 `mirror_frames` 是**逐帧翻转**而非整条倒放 —— 倒放会让动画倒着播:
   `agent/pet/generate/atlas.py:1038 @ 863e313`
   ```
def mirror_frames(frames: list) -> list:
    """Horizontally flip each frame *in place* (RGBA-safe).

    Used to derive ``running-left`` from an approved ``running-right`` row. The
    flip is per-frame so the leftward loop preserves the rightward loop's frame
    order and timing — this is NOT a whole-strip reverse (which would play the
    animation backwards), matching the petdex/Codex mirror rule.
   ```
4. **idle 兜底**:idle 行生成失败就拿 base 图当唯一 idle 帧,保证宠物一定渲染得出来。
5. **验收门槛**:`validate_atlas` 通过 + `_REQUIRED_STATES` 三行齐全 + 填充状态数 ≥6,
   否则抛错、**不落盘**。
6. **协作式取消**:`is_cancelled` 在每个 future 前后轮询;取消后在 compose/save **之前**
   抛错,所以"停止"永远不会写出一只半成品宠物。
   另外 `as_completed` 循环刻意跑在调用方线程上,好让 `on_draft` / `progress` 发出的
   网关事件继承请求绑定的 transport(注释见上面那个块的末行,以及 `generate_base_drafts`
   里同形状的一处)。

**报错人性化**是个容易被忽略的细节:草稿全挂时不说"no usable drafts",而是取最高频错误
翻译成人话 —— 图像模型对商标角色/真人的内容审核拒绝是最常见的一种:
`agent/pet/generate/orchestrate.py:176 @ 863e313`
```
def _humanize_image_error(error: str) -> str:
    """Turn a raw provider error into a friendly, actionable sentence.

    The big one is moderation: image models refuse trademarked characters and
    real people (e.g. "minion"), which reads as an opaque 400 otherwise.
    """
```

### 3.3 `prompts.py`:提示词长什么样、怎么保证风格一致

**两种形状**:`build_base_prompt`(纯文本 → 单张定妆照)、`build_row_prompt`
(定妆照当参考图 → 一条横向 N 帧动作条)。

风格一致靠**四层叠加**,而不是靠"写得漂亮":

1. **参考图接地(最强的一层)**:行提示词第一句就把参考图钉成同一角色 ——
   `agent/pet/generate/prompts.py:149 @ 863e313`
   ```
    return (
        f"Using the attached reference image as the exact same character "
        f"(same species, face, colors, markings, proportions, and props), "
        "preserving the same emotional tone/mood (e.g., scary stays scary, cute stays cute), "
        f"draw a single WIDE horizontal strip of {frame_count} animation frames showing {action}. "
   ```
2. **色键背景段(全簇共用一段常量)**,同时禁掉分栏线/网格/阴影这些会毁掉切帧的东西:
   `agent/pet/generate/prompts.py:65 @ 863e313`
   ```
_BACKGROUND = (
    "Center the character on a SINGLE flat, uniform, high-contrast chroma-key "
    "background — pure hot magenta #FF00FF (only if magenta appears on the "
    "character, use pure green #00FF00 instead). The background is ONE continuous "
    "even color that completely surrounds the character with NO gradient, "
    "vignette, texture, pattern, scenery, shadow, ground line, frame, border, "
    "panel, comic cell, gutter line, grid, or divider of any kind, so it keys out "
    "cleanly. The background color must not appear anywhere on the character. "
    "No text, no labels, no speech bubbles, no UI."
)
   ```
   注意"若角色身上有洋红就改用纯绿"这条 —— 色键失效的经典成因。
3. **REGISTRATION 段(反抖动的提示词侧)**:要求每帧同高同宽同基线,只有动作需要的肢体动。
   这与 `normalize_cells` 的相位相关是**同一问题的两道防线**。
4. **风格提示表 + 每草稿的差异化 nudge**:`_STYLE_HINTS["auto"]` 明确顶住 gpt-image
   默认往 3D/插画跑的倾向;`BASE_VARIATIONS` 六条只改**外观**(配色/体型/表情)不改姿势 ——
   `agent/pet/generate/prompts.py:104 @ 863e313`
   ```
# Per-draft nudges so the 4 base options are actually distinct — gpt-image returns
# near-duplicates for a single prompt. We vary the *look* (palette, build,
# expression, accents), NOT the pose, so the chosen base still grounds clean,
# consistent animation rows.
   ```

还有一个我认为最值得抄的细节:**间距不用绝对像素讲,用"比例包容"讲**。

`agent/pet/generate/prompts.py:87 @ 863e313`
```
def _spacing_spec(frame_count: int) -> tuple[int, int]:
    """(per-pose width px, gap px) for a row of *frame_count* poses.

    Pixel counts alone don't hold — the model fills each slot edge-to-edge with
    the full wingspan, so neighbors touch even when bodies are spaced. The lever
    that works is proportional containment on a wide canvas: give each pose its
    own equal cell and keep the ENTIRE silhouette (wings/tail/halo included)
    inside it. On the 1536px landscape strip ~70% occupancy still leaves a
    generous gutter, so the pet stays a normal, good-looking size — no shrinking.
    """
```
这是"提示词工程"里少见的、把**失效模式**和**有效杠杆**都写清楚的注释。

---

## 4. 状态与存储

### 4.1 `state.py`(81 行)与 `store.py`(503 行)的分工

**名字很容易误导:`state.py` 不是"宠物状态",`store.py` 也不是"状态存储"。**

- `state.py` = **活动 → 动画行的映射**(无状态纯函数,见 1.1(b))。
  另有 `todos_all_done`,把"计划全部完成 → 庆祝跳跃"这个触发条件定义在一处,
  给 CLI / TUI / 桌面三端共用。
- `store.py` = **磁盘上的宠物资产管理**。宠物本身没有可演进的状态,所以"持久化"的
  全部内容就是资产:`pets/<slug>/pet.json` + `pets/<slug>/spritesheet.webp`。

### 4.2 宠物状态怎么演进

**不演进。** 每次渲染都是 `derive_pet_state(...)` 从当前活动信号现算,不读任何历史。
唯一的"时间"成分在 CLI 的瞬时反应节拍上 —— 转身结束时闪一下 wave/jump/failed,
1.6 秒后回落:
`cli.py:5682 @ 863e313`
```
    def _pet_flash(self, state: str, secs: float = 1.6) -> None:
        """Briefly force a transient reaction (wave/jump/failed) before resting."""
        self._pet_event = state
        self._pet_event_until = time.monotonic() + secs
```
这个 flash 只活在**内存里**,进程退出即消失。

### 4.3 持久化在哪、格式是什么

`agent/pet/store.py:1 @ 863e313`
```
"""On-disk pet store — install / list / resolve pets.

Pets live under ``get_hermes_home()/pets/<slug>/`` so every profile gets its
own set (we deliberately do **not** reuse petdex's ``~/.codex/pets`` default —
that's owned by the petdex npm CLI and isn't profile-aware).  Each installed
pet directory holds:

    pets/<slug>/
        pet.json            # {id, displayName, description, spritesheetPath}
        spritesheet.webp    # (or .png)
```

额外的两个位置:缩略图缓存目录 `pets/.thumbs/`,以及生成的宠物在 `pet.json` 里多带的
`createdBy` 字段 ——

`agent/pet/store.py:263 @ 863e313`
```
    meta = {
        "id": slug,
        "displayName": display_name or slug,
        "description": description or "",
        "spritesheetPath": sprite_path.name,
        "createdBy": "generator",
    }
```

`agent/pet/store.py:307 @ 863e313`
```
def _thumbs_dir() -> Path:
    path = pets_dir() / ".thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

`createdBy == "generator"` 就是 `InstalledPet.generated` 属性的全部依据
(`store.py` 里 `generated` 的定义在 `InstalledPet` 上),桌面端据此把"自己孵的"和
"从图库装的"分开显示。

### 4.4 并发 / 损坏怎么处理

**这是本簇最"工程"的一节,五条:**

1. **下载走临时文件 + 原子替换**,所以中断不会留下半张精灵表:
   `agent/pet/store.py:481 @ 863e313`
   ```
        ) as resp:
            resp.raise_for_status()
            tmp = dest.with_suffix(dest.suffix + ".part")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
            tmp.replace(dest)
   ```
2. **坏 `pet.json` 一律降级为空 dict,不抛**,之后所有字段取值都有 `or <fallback>`,
   最坏情况是显示名回落成 slug:
   `agent/pet/store.py:63 @ 863e313`
   ```
def _read_pet_json(directory: Path) -> dict:
    pet_json = directory / "pet.json"
    if not pet_json.is_file():
        return {}
    try:
        return json.loads(pet_json.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.debug("unreadable pet.json in %s: %s", directory, exc)
        return {}
   ```
3. **精灵表缺失也返回稳定路径**,让调用方拿到确定的 `Path` 而不是 `None`
   (`_resolve_spritesheet` 末尾 `return directory / "spritesheet.webp"`)。
4. **路径穿越守卫**(两处,互相独立):
   `agent/pet/store.py:93 @ 863e313`
   ```
def _safe_slug(slug: str) -> str:
    """Normalize a slug to a single bare path segment.

    Pet slugs index into ``pets_dir()/<slug>/`` for load/remove, so a value
    carrying path separators (``../``, absolute paths) could escape the pets
    directory. Strip every separator and reject ``.``/``..`` so callers can
    only ever name a direct child of the pets directory.
    """
    segment = Path(str(slug).strip()).name
    if segment in ("", ".", ".."):
        return ""
    return segment
   ```
   以及 `export_pet` 里的 `directory.resolve().parent != root.resolve()` 检查。
5. **SSRF 守卫**:清单虽然来自 HTTPS 的 petdex.dev,资产 URL 仍然**逐条钉主机**:
   `agent/pet/store.py:313 @ 863e313`
   ```
def _is_petdex_host(url: str) -> bool:
    """True only for petdex.dev hosts — bounds server-side fetch (anti-SSRF)."""
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host == "petdex.dev" or host.endswith(".petdex.dev")
   ```
   理由写得很清楚:清单可信不等于清单里的 URL 可信 —— 一个被篡改的清单不该能把
   网关的下载指向任意主机。**这是"cosmetic 功能也要走安全评审"的样板。**

**没有锁。** 整个 store 没有任何文件锁或进程锁(搜索面:`grep -n "lock\|flock\|fcntl" agent/pet/store.py`
只命中 0 处;全簇唯一的 `threading.Lock` 在 `agent/pet/manifest.py` 的预取去重里)。两个进程同时
`install_pet` 同一个 slug 会互相覆盖 —— 但因为写的是同一份内容且末次写入原子,
后果止于重复下载。**这是一个被有意接受的取舍,不是遗漏**(资产是幂等内容寻址的)。

### 4.5 `manifest.py`:进程内 TTL 缓存 + 后台预取

`agent/pet/manifest.py:34 @ 863e313`
```
# In-process cache for the (large, slow, identical-per-call) manifest. The list
# is a static CDN object that barely changes, yet a single session can ask for
# it many times — every gallery open, plus a full re-fetch per install/select
# (``find_entry``). A short TTL collapses those into one network hit without
# going stale for long. Cleared by :func:`clear_cache` (tests).
_MANIFEST_TTL = 300.0
```
`prefetch()` 用 daemon 线程 + 一个 bool 去重,幂等且永不阻塞:

`agent/pet/manifest.py:56 @ 863e313`
```
def prefetch(*, timeout: float = _DEFAULT_TIMEOUT) -> None:
    """Warm the manifest cache in a daemon thread — idempotent, never blocks.

    The desktop picker calls this when it loads the (instant) local-only gallery
    so the full petdex catalog is usually cached by the time it's requested,
    without ever holding up the user's own pets on a network round-trip.
    """
```

即桌面选择器先秒开本地宠物,公共图库在背景热身;异常一律吞进 debug 日志。

---

## 5. 渲染 `render.py`(682 行)

### 5.1 渲染到哪:**终端**(四种协议),不是图片文件

`agent/pet/render.py:40 @ 863e313`
```
# Public render-mode names accepted by ``display.pet.render_mode``.
RENDER_MODES = ("auto", "kitty", "iterm", "sixel", "unicode", "off")
```

按保真度:`kitty`(kitty/Ghostty/WezTerm 的图形协议)> `iterm`(iTerm2 OSC 1337 内联图)
> `sixel`(DEC sixel,**Pillow 没有 sixel 写出器,这里是手写编码器 `_encode_sixel`**)
> `unicode`(24-bit 半块降采样,任何真彩终端都能用)。

**能力探测只看环境变量,绝不向终端发查询**:
`agent/pet/render.py:49 @ 863e313`
```
    """Best-effort detection of the richest graphics protocol available.

    Env-based (non-blocking — we never issue a DA1/terminal query that could
    hang a pipe).  Returns one of ``kitty`` / ``iterm`` / ``sixel`` /
    ``unicode``.  Conservative: unknown terminals get ``unicode``, which works
    anywhere with truecolor.
    """
```
这条设计取舍值得记:DA1 查询能拿到准确答案,但在管道/非交互环境会挂住。
作者选了"猜错了顶多难看,永不挂住"。

**VS Code 的坑单独处理**(有测试守着,见 §7 表里的
`test_vscode_terminal_ignores_leaked_graphics_env`):
`agent/pet/render.py:59 @ 863e313`
```
    # The VS Code / Cursor integrated terminal sets TERM_PROGRAM=vscode
    # authoritatively but does NOT scrub the terminal env vars it inherits when
    # launched from another emulator (ITERM_SESSION_ID, KITTY_WINDOW_ID, …).
    # Trusting those leaks emits an image protocol the embedded xterm.js can't
    # display — you get a blank frame. Inline images there are opt-in
    # (terminal.integrated.enableImages), so default to half-blocks, which
    # always render in its truecolor grid. Users who enabled images can pin
    # display.pet.render_mode explicitly.
```

**非 TTY 一律关掉**:
`agent/pet/render.py:104 @ 863e313`
```
        return "off"

    stream = stream or sys.stdout
    try:
        if not (hasattr(stream, "isatty") and stream.isatty()):
            return "off"
    except (ValueError, OSError):
        return "off"

    if mode == "auto":
        return detect_terminal_graphics()
    return mode
```

### 5.2 与 `agent/display.py` 的关系:**没有关系**

```verify
cd /home/user/hermes-agent
grep -ci "pet" agent/display.py          # 期望 0(整个文件不含 "pet" 这三个字母)
grep -rn "agent\.display\|from agent import display" agent/pet/ --include="*.py" | wc -l
```

两条都是 `0`。**搜索面与排除项**:只搜了 `agent/display.py` 的全文(不区分大小写、
连 `snippet`/`competitive` 这类子串命中都算),以及 `agent/pet/**.py` 里对 `agent.display`
的 import。结论:**pet 渲染完全绕开主 CLI 的显示层**。

它们的实际关系是**同级并列**:`agent/display.py` 负责工具调用/消息的格式化输出,
pet 是 prompt_toolkit 布局里另一个独立的 `Window`(见 §1.2 引的 `self._pet_widget`)。
CLI 侧还刻意**只用半块**、不用 kitty:
`cli.py:5615 @ 863e313`
```
    # Parity with the TUI: a half-block sprite rendered as a prompt_toolkit
    # window above the prompt, reacting to agent state and animated by a timer
    # that calls ``app.invalidate()``. Half-blocks only — the crisp Kitty image
    # protocol can't coexist with prompt_toolkit's patch_stdout output layer
    # (raw image escapes get swallowed/mangled), so we use truecolor styled
    # text, which prompt_toolkit renders natively in any 24-bit terminal.
```
**取舍很清楚:在会被 prompt_toolkit 重绘的区域里,只能用它认得宽度的文本。**

### 5.3 帧解码:两级 `lru_cache` + 空白帧裁剪

`agent/pet/render.py:129 @ 863e313`
```
# Max alpha at/below which a frame counts as blank padding.  petdex sheets are
# left-packed: a state with fewer real frames than ``FRAMES_PER_STATE`` fills
# the trailing columns with fully transparent cells.  Animating into one flashes
# the pet blank, so we stop the row at the first such gap.
_BLANK_ALPHA = 8


def _frame_is_blank(frame) -> bool:
    """True if *frame* has no meaningfully opaque pixel (transparent padding)."""
    return frame.getchannel("A").getextrema()[1] <= _BLANK_ALPHA
```

`_raw_frames`(`lru_cache(maxsize=16)`,裁剪+去尾padding)→ `_frames_for`
(`lru_cache(maxsize=8)`,加缩放)。行数由**实际精灵表的形状**决定,不是常量:
`_raw_frames` 里 `cols = sheet.width // frame_w`、`rows = sheet.height // frame_h`,
再交给 `state_row_index(state_value, rows)` 选行 —— 这正是"同时支持 8 行旧表和 9 行新表"
的落点。行为规格见 §7 表里的
`test_trims_trailing_blank_frames`,它用一张各行帧数参差的合成表,断言 wave=4 / jump=5 /
review=5 且每一帧都非空。

### 5.4 kitty Unicode 占位符:为 Ink 网格准备的特殊通路

`agent/pet/render.py:325 @ 863e313`
```
# Ink (the TUI's React-for-terminal layer) owns the screen and measures every
# cell's width, so it can't host raw kitty image escapes (no width to count,
# clobbered on the next repaint). kitty's *Unicode placeholder* protocol is the
# grid-safe path: transmit the image once (q=2, virtual placement U=1), then the
# host app prints ordinary-width placeholder cells (U+10EEEE + diacritics) whose
# foreground color encodes the image id. Ink counts those as width-1 text, so
# layout stays correct and the terminal paints the image underneath.
```

图片 id 用 slug 的 CRC32 取模得到,保证同一只宠物重绘时复用终端侧的同一张图:

`agent/pet/render.py:374 @ 863e313`
```
def kitty_image_id(slug: str) -> int:
    """Stable per-pet image id in ``[1, 0x7FFF]``.

    The id is encoded in the placeholder's 24-bit foreground color, so it must
    be non-zero and fit comfortably under ``0xFFFFFF``. A small CRC keeps it
    deterministic per slug (so re-renders reuse the same terminal-side image)
    while making collisions between two different pets unlikely.
    """
    import zlib

    return (zlib.crc32(slug.encode("utf-8")) % 0x7FFE) + 1
```

id 再编码进占位符的 24-bit 前景色(`kitty_color_hex`)。文件里还逐字抄了 kitty 的
297 个行列变音符号表 `_ROWCOL_DIACRITICS` —— **这一段 32 行占了 render.py 的 4.7%,
是一张纯数据表**。

kitty 路径上还有两个"像素完美"补丁。其一,kitty 会把整个传输矩形画出来,
透明边距会让宠物看起来又小又飘,所以按并集不透明框统一裁掉:

`agent/pet/render.py:253 @ 863e313`
```
def _crop_frames_to_alpha_union(frames):
    """Crop every frame to the union opaque bbox so the sprite hugs its box.

    kitty paints the whole transmitted rectangle, transparent margins included,
    which makes the visible pet look small and adrift inside a larger cell box.
    Trimming to the visible bounds keeps the pet tight in its corner.
    """
    bbox = _union_alpha_bbox(frames)
    if not bbox:
        return frames
    return [f.crop(bbox) for f in frames]
```

其二,把帧尺寸吸附到 8×16 的整数倍,否则 kitty 向上取整会**切掉宠物的脚**并留一条空行:

`agent/pet/render.py:266 @ 863e313`
```
# Nominal terminal cell size in pixels. kitty fits an image to its cell
# rectangle preserving aspect, so a frame whose pixel size isn't a whole
# multiple of the cell rounds up — which makes the terminal clip the bottom row
# (the "clipped feet") and letterbox a blank row. Snapping each frame to an
# exact cell multiple avoids that. (See ratatui-image #57: "render in multiples
# of the font-size, to avoid stale character artifacts.")
_CELL_W = 8
_CELL_H = 16
```

行为规格见 §7 表里的 `test_kitty_payload_structure`,
它逐条断言转义串以 `\x1b_G` 开头、含 `a=T` / `U=1` / `i=<id>` / `c=` / `r=`。

### 5.5 半块降采样:框架中立的中间表示

`_downscale_cells` 返回 `list[list[Cell]]`,`Cell = ((r,g,b,a) 上, (r,g,b,a) 下)`。
两个消费者:CLI/`pets show` 走 `_encode_unicode` 拼 ANSI 串;TUI 走
`PetRenderer.cells()` 拿结构化数组,由 Ink 用原生颜色属性画。
**同一份降采样,两种编码** —— 这就是包 docstring 里 "the decode +
capability-detection + protocol-encoding logic exists exactly once" 的实现方式。

---

## 6. 配置项与环境变量

### 6.1 配置键(全部在 `display.pet` 下,共 5 个)

| 键 | 默认 | 定义处(锚点:摘录) | 消费点 |
|---|---|---|---|
| `display.pet.enabled` | `False` | `hermes_cli/config_defaults.py:1287`:`"enabled": False,` | `cli.py` / `pet.cells` / 桌面 |
| `display.pet.slug` | `""` | `hermes_cli/config_defaults.py:1290`:`"slug": "",` | `store.resolve_active_pet` |
| `display.pet.render_mode` | `"auto"` | `hermes_cli/config_defaults.py:1294`:`"render_mode": "auto",` | `render.resolve_mode` |
| `display.pet.scale` | `0.33` | `hermes_cli/config_defaults.py:1300`:`"scale": 0.33,` | 三端共用的**唯一尺寸主标量** |
| `display.pet.unicode_cols` | `0` | `hermes_cli/config_defaults.py:1304`:`"unicode_cols": 0,` | `constants.resolve_cols` 的硬覆盖 |

`scale` 的"一个旋钮管三端"是本簇的设计亮点,而且**注释解释了为什么它在半块下不完全等效**:
`agent/pet/constants.py:54 @ 863e313`
```
# Legibility floor for the half-block fallback.  A half-block cell samples the
# sprite at only 1 horizontal + 2 vertical taps, so below this width a 192×208
# pet collapses into an unreadable blob *regardless* of scale.  kitty/GUI draw
# true pixels and have no such floor — that's why the same ``scale: 0.33`` is
# crisp there but mush in half-blocks.  ``scale`` shrinks the unicode pet down
# TO this floor (and grows it above), instead of past it into noise.
UNICODE_MIN_COLS = 16
```
边界 `MIN_SCALE=0.1` / `MAX_SCALE=3.0`,`clamp_scale` 是**唯一校验点**,
而唯一写入路径是:

`hermes_cli/pets.py:337 @ 863e313`
```
def set_pet_scale(value: float | str) -> tuple[float, str | None]:
    """Set ``display.pet.scale`` (clamped to bounds). Returns ``(applied, error)``.

    The single write path behind ``/pet scale`` and the desktop slider, so every
    surface that resolves scale from config picks it up identically. *error* is
    set (and nothing written) only when *value* isn't a number.
    """
    from agent.pet.constants import clamp_scale

    try:
        scale = clamp_scale(float(value))
    except (TypeError, ValueError):
        return 0.0, f"not a number: {value!r} — try a value like 0.5"

    _set_scale(scale)
    return scale, None
```

`/pet scale`、`hermes pets scale`、桌面滑块三条路都收敛到这一个函数。

### 6.2 环境变量(全仓只有 2 个 `HERMES_PET_*`)

```verify
cd /home/user/hermes-agent
grep -rhoE "HERMES_PET_[A-Z_]+" --include="*.py" --include="*.ts" --include="*.tsx" \
    --include="*.md" . | sort -u
```

```text
HERMES_PET_IMAGE_PROVIDER
HERMES_PET_REFERENCE_MAX_BYTES
```

- `HERMES_PET_IMAGE_PROVIDER` —— QA 覆盖,只对 pet 生成生效,取值必须在 `_REF_CAPABLE` 内,
  否则**静默忽略**:

  `agent/pet/generate/imagegen.py:40 @ 863e313`
  ```
def _forced_provider_from_env() -> str | None:
    """Optional QA override to force a pet-gen backend.

    `HERMES_PET_IMAGE_PROVIDER=<name>` (e.g. `openrouter`) bypasses the normal
    active/default provider resolution for pet generation only. Unknown values are
    ignored so existing users are unaffected.
    """
    forced = os.environ.get("HERMES_PET_IMAGE_PROVIDER", "").strip().lower()
    return forced if forced in _REF_CAPABLE else None
  ```

  已被用户文档收录:

  `website/docs/user-guide/features/pets.md:124 @ 863e313`
  > - Override the backend with the `HERMES_PET_IMAGE_PROVIDER` env var (e.g. `HERMES_PET_IMAGE_PROVIDER=openrouter`).
- `HERMES_PET_REFERENCE_MAX_BYTES` —— 网关侧参考图上传上限,默认 16 MiB。
  `tui_gateway/server.py:8233 @ 863e313`
  ```
try:
    _PET_REFERENCE_MAX_BYTES = max(
        1,
        int(os.environ.get("HERMES_PET_REFERENCE_MAX_BYTES") or str(16 * 1024 * 1024)),
    )
except (TypeError, ValueError):
    _PET_REFERENCE_MAX_BYTES = 16 * 1024 * 1024
  ```
  **任何 `.md` 都没有提它**(见 ◇-1)。

另有一个测试门控变量 `HERMES_RUN_SLOW_PET_TESTS`(见第 7 节)。

---

## 7. 测试作为行为规格

5 个文件,实测全绿。

```verify
cd /home/user/hermes-agent
HERMES_PYTHON=/home/user/hermes-venv/bin/python bash scripts/run_tests.sh \
  tests/agent/test_pet_engine.py tests/hermes_cli/test_pet_toggle.py \
  tests/cli/test_cli_pet_pane.py tests/tui_gateway/test_pet_generate_rpc.py
HERMES_RUN_SLOW_PET_TESTS=1 HERMES_PYTHON=/home/user/hermes-venv/bin/python \
  bash scripts/run_tests.sh tests/agent/test_pet_generate.py
```

```text
=== Summary: 4 files, 15 tests passed, 0 failed (100% complete) in 1.8s (8 workers) ===
=== Summary: 1 files, 11 tests passed, 0 failed (100% complete) in 18.8s (8 workers) ===
```

**环境(按 CLAUDE.md 要求记):** venv `/home/user/hermes-venv`,`pip list` 去表头
**89 个包**、`*.dist-info` 目录 **89 个**(两数一致)。
注意这**比 CLAUDE.md 记录的 87 多 2 个**:`anthropic-0.87.0` 与 `docstring_parser-0.18.0`
的 dist-info 时间戳是 `Aug 9 04:51`,而 `[dev]` + `aiohttp` + `brotlicffi` 那批是 `04:27` ——
即本轮开工前有别的会话往共享 venv 装过东西。本簇测试不依赖这两个包,数不受影响,
但按"直接断言而非间接推断"的规矩记在这里。

**`tests/agent/test_pet_generate.py` 默认整文件跳过**,要 opt-in:
`tests/agent/test_pet_generate.py:14 @ 863e313`
```
pytestmark = pytest.mark.skipif(
    os.environ.get("HERMES_RUN_SLOW_PET_TESTS") != "1",
    reason=(
        "pet generation image-processing suite is opt-in; run with "
        "HERMES_RUN_SLOW_PET_TESTS=1 scripts/run_tests.sh tests/agent/test_pet_generate.py"
    ),
)
```
门控实测有效:不带该变量时同一文件报 `11s`(11 skipped)/ `0 tests passed`;
带上时 `11✓` / 18.8s。**代价:这 11 条覆盖 atlas 全流水线的用例在日常 CI 里是不跑的**
(见移交项 H-R9B-3)。

**被当作行为规格引用的用例(锚点:摘录):**

| 用例 | 钉住的规格 |
|---|---|
| `tests/agent/test_pet_engine.py:24`:`def test_derive_priority_order():` | 8 级优先序,尤其 `awaiting_input` 压过 `tool_running` |
| `tests/agent/test_pet_engine.py:61`:`def test_state_row_index_maps_to_supported_atlas_taxonomies():` | 9 行/8 行两套分类法 + 别名 + 未知名回落 row 0 |
| `tests/agent/test_pet_engine.py:135`:`def test_trims_trailing_blank_frames(tmp_path):` | 参差行裁到真实帧数,不闪空白 |
| `tests/agent/test_pet_engine.py:242`:`def test_vscode_terminal_ignores_leaked_graphics_env(monkeypatch):` | `TERM_PROGRAM=vscode` 压过泄漏的 KITTY/ITERM 变量 |
| `tests/agent/test_pet_generate.py:60`:`def test_remove_background_defringes_antialiased_edge():` | 抠图后轮廓每边约削 1px、核心完好 |
| `tests/agent/test_pet_generate.py:113`:`def test_validate_atlas_rejects_postage_stamp_sprite():` | "邮票化"图集必须被拒 |
| `tests/agent/test_pet_generate.py:233`:`def test_hatch_pet_end_to_end(monkeypatch, tmp_path):` | 全 9 行齐全 + 落盘可采纳 |
| `tests/cli/test_cli_pet_pane.py:87`:`def test_pet_pane_collapsed_when_disabled():` | 未启用时窗口高度 0、无 fragment |
| `tests/hermes_cli/test_pet_toggle.py:61`:`def test_set_pet_scale_writes_clamped_value(empty_home):` | 越界不报错,夹到 `[0.1, 3.0]` |

---

## 8. 定案

### ■-1 `hermes pets show --cycle` 只循环 7 个状态里的 4 个(别名映射漏做)

`hermes_cli/pets.py:177 @ 863e313`
```
    # Which states to play: one named state, or cycle the driveable rows.
    requested = (getattr(args, "state", "") or "").strip().lower()
    if requested:
        states = [requested]
    elif getattr(args, "cycle", False):
        states = [s for s in STATE_ROWS if s in {e.value for e in PetState}]
    else:
        states = [PetState.IDLE.value]
```

`STATE_ROWS` 现在指向 **`CODEX_STATE_ROWS`**:

`agent/pet/constants.py:122 @ 863e313`
```
# Default/fallback for callers without a sheet. Prefer the current 9-row Codex
# format because generated pets and the public Codex pet contract use it.
STATE_ROWS: list[str] = CODEX_STATE_ROWS
```

里面写的是图集行名
`running-right / running-left / waving / jumping / running`;而 `{e.value for e in PetState}`
是 Hermes 活动名 `wave / jump / run`。**两套名字正是 `STATE_ALIASES` 存在的理由**,
这句列表推导却直接做集合交,于是三个有别名的状态全被筛掉。实测:

```verify
cd /tmp && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/user/hermes-agent \
  /home/user/hermes-venv/bin/python -c "
from agent.pet.constants import STATE_ROWS, PetState, LEGACY_STATE_ROWS
print([s for s in STATE_ROWS if s in {e.value for e in PetState}])
print([s for s in LEGACY_STATE_ROWS if s in {e.value for e in PetState}])
"
```

```text
['idle', 'failed', 'waiting', 'review']
['idle', 'wave', 'run', 'failed', 'review', 'jump']
```

**缺 `wave` / `jump` / `run`。** 第二行说明这是一处**回归**:在旧的 8 行分类法下
同一句话能给出 6 个状态,`STATE_ROWS` 从 LEGACY 切到 CODEX 后它悄悄退化了。
修法一行:`states = [s.value for s in PetState]`,或用 `state_aliases_for` 反查。

顺带:argparse 帮助与用户文档都声称它遍历全部状态 ——
`hermes_cli/pets.py:484 @ 863e313`
```
    p_show.add_argument("--cycle", action="store_true", help="Cycle through all states")
```
`website/docs/user-guide/features/pets.md:86 @ 863e313`
> - `--cycle` — cycle through every state.

**这里文档是对的、代码是错的,所以计 ■ 不计 ▲。** 影响面:仅预览命令,不影响实际渲染
(实际渲染由 `derive_pet_state` 直接给 `PetState`,不经这句)。

### ■-2 `imagegen.py` 的开篇 docstring 有一半与同仓 schema 矛盾

`agent/pet/generate/imagegen.py:1 @ 863e313`
```
"""Thin image-generation layer for pet sprites.

Wraps the active :class:`~agent.image_gen_provider.ImageGenProvider` with the
two things sprite generation needs that the agent-facing ``image_generate`` tool
doesn't expose: **N variants** (loop) and **reference-image grounding** (so each
animation row stays the same character as the chosen base).
```

但模型可见的 `image_generate` schema **恰恰暴露了** `reference_image_urls`:

`tools/image_generation_tool.py:1207 @ 863e313`
```
            "reference_image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of additional reference image URLs / paths "
                    "(style, character, or composition references) to guide an "
                    "image-to-image edit. Supported only by some models and "
                    "capped per-model; the description above indicates the max."
                ),
            },
```

前半句("N variants" 未暴露)成立 —— schema 的 `properties` 只有
`prompt / aspect_ratio / image_url / reference_image_urls`,没有 `num_images`。
**所以这是"半句为真"型的过时自述**:另起一套的真实理由是 N 变体 + 透明背景探测
+ 双 kwarg 名 + 参考能力白名单,而不是"工具不支持参考图"。
计 ■ 而非 ▲,因为它是代码里的 docstring,不属于 CLAUDE.md 定义的"作者自绘地图"范围;
标注为**文档性缺陷,非运行时 bug**。

### ▲-1 `pets.md` 说"six animation states",实为 7

`website/docs/user-guide/features/pets.md:25 @ 863e313`
> - Each surface watches the activity it already tracks and maps it to one of six
>   animation states. The mapping lives in one place so every surface behaves the
>   same:

**整段判定**(按 CLAUDE.md 要求把整句连同它所辖的表一并判):这句话之后紧跟的表格
自己就列了 8 行、**7 个互异状态**(failed / jump / wave / run / review / waiting / idle),
其中 `waiting` 那行还带着"legacy 8 行表回落 idle"的注脚 —— 也就是说**文档正文的数字
与文档自己的表格矛盾**,更与代码矛盾:

`agent/pet/constants.py:78 @ 863e313`
```
class PetState(str, Enum):
    """Animation state a pet can be shown in.

    These are Hermes' activity state names. They are not always identical to the
    source atlas row names: Codex-format pets use rows like ``jumping`` /
    ``running`` while the UI keeps the shorter ``jump`` / ``run`` names.
    """

    IDLE = "idle"
    WAVE = "wave"
    RUN = "run"
    FAILED = "failed"
    REVIEW = "review"
    JUMP = "jump"
    WAITING = "waiting"

```

"one of six" 是**精确计数断言**、字面为假,故记 ▲ 而非 ◎。

**归属标题(按 CLAUDE.md 要求确认这条断言归谁管):**

`website/docs/user-guide/features/pets.md:18 @ 863e313`
> ## How it works

同一篇同一节之外,`--state` 的取值枚举也漏了 `waiting` —— 同一次 `waiting` 增补没扫干净:

`website/docs/user-guide/features/pets.md:84 @ 863e313`
> - `--state` — play a single state (`idle`, `wave`, `run`, `failed`, `review`,
>   `jump`).

### ◎-1 `pets.md` 的参考图后端清单少一个(4 vs 5),但所列全为真

`website/docs/user-guide/features/pets.md:120 @ 863e313`
> Generation uses the active [image-generation provider](/user-guide/features/image-generation), but it requires **reference-image grounding** so each animation row stays the same character as the base. Reference-capable backends: **Nous Portal**, **OpenRouter**, **OpenAI** (`gpt-image-2`), and **Krea**. OpenRouter/Nous run a quality-first model chain by default.

代码里 `_REF_CAPABLE` 有 5 个(见 3.1 摘录),多出的是 `openai-codex`
(标签 `"OpenAI (Codex)"`)。**所列 4 个逐一为真**,紧跟的偏好序描述也与
`_REF_CAPABLE` 的相对次序一致:

`website/docs/user-guide/features/pets.md:122 @ 863e313`
> - Resolution order prefers Nous Portal → OpenAI → OpenRouter.

只是枚举不完整 —— 按 CLAUDE.md 的口径,字面为真就不是 ▲,记 ◎(保守但成立)。

**归属标题:**

`website/docs/user-guide/features/pets.md:118 @ 863e313`
> ### Image backend

### ◇-1 `HERMES_PET_REFERENCE_MAX_BYTES` 代码有、文档无

```verify
cd /home/user/hermes-agent
grep -rn "HERMES_PET_REFERENCE_MAX_BYTES" --include="*.md" . | wc -l
```
结果 `0`。**搜索面**:全仓所有 `.md`(含 `website/docs/**`、`skills/**`、README、AGENTS.md)。
定义处见 6.2 的摘录。一个用户可调、影响桌面端"上传自己的图当参考"能否成功的上限,
只活在代码里。

### ◇-2 三个只有网关 RPC 能用的能力,CLI 与文档都没有

| 能力(锚点:摘录) | 暴露给谁 |
|---|---|
| `agent/pet/store.py:278`:`def export_pet(slug: str) -> tuple[str, bytes]:` | 仅 `pet.export` RPC |
| `agent/pet/store.py:422`:`def rename_pet(slug: str, display_name: str) -> str` | 仅 `pet.rename` RPC |
| `agent/pet/store.py:324`:`def thumbnail_png(slug: str, *, source_url: str = "", timeout: float = 30.0) -> bytes` | 仅 `pet.thumb` RPC |

三者都只有桌面端能用,但:

```verify
cd /home/user/hermes-agent
# 面:hermes pets 的子命令注册表 + 两份用户文档
grep -nE "add_parser\(" hermes_cli/pets.py
grep -rniE "\bexport\b|\brename\b|thumbnail" website/docs/user-guide/features/pets.md \
    website/docs/reference/cli-commands.md \
    skills/autonomous-ai-agents/hermes-agent/references/petdex.md | wc -l
```
第二条为 `0`。**排除项**:未搜桌面端 TS 文案(`apps/desktop/**`),那是 UI 内文字不是仓库文档。
即 `hermes pets` 只有 list/install/select/show/off/scale/remove/doctor 八个子命令,
导出/改名/缩略图**没有 CLI 对等物,也没有任何文档**。这不是缺陷,是"桌面优先"的能力分布,
但对着文档学习的人会看不到这三个能力的存在。

### ◇-3 `rename_pet` 会连带改目录名与 slug —— 这个副作用没有任何文档

`agent/pet/store.py:422 @ 863e313`
```
def rename_pet(slug: str, display_name: str) -> str | None:
    """Rename a pet's ``displayName`` AND realign its slug/dir to match.

    Generated pets are hatched under a provisional, prompt-derived slug; when
    the user names the pet on the reveal screen we make that name the real
    identity so lists/subtitles show what they typed, not the prompt. The dir is
    renamed to ``slugify(name)`` (and the cached thumbnail moved alongside it)
    whenever that yields a free, different slug — otherwise the slug is left as
    is. Returns the resulting slug on success, or ``None`` on failure.
    """
```
配套地,`hermes_cli/pets.py:419` 的 `_rename_active_if` 必须把 `display.pet.slug`
跟着改掉,否则配置会指向一个已经不存在的目录。**这是一条"改名不是纯元数据操作"的
隐藏契约**,只存在于 docstring 里。

---

## 9. 移交项

| 编号 | 锚点(锚点:摘录) | 一句话现象 | 建议 |
|---|---|---|---|
| H-R9B-1 | `hermes_cli/pets.py:182`:`states = [s for s in STATE_ROWS if s in {e.value for e in PetState}]` | `--cycle` 实测只产出 `['idle','failed','waiting','review']`,漏 wave/jump/run(■-1) | 若 R10+ 做"回归型缺陷"专题,这是一个干净样本:同一行代码在 `STATE_ROWS` 换值前后行为不同 |
| H-R9B-2 | `agent/pet/generate/imagegen.py:4`:`two things sprite generation needs that the agent-facing ``image_generate`` tool` | docstring 称 agent 面工具不暴露参考图接地,但 `IMAGE_GENERATE_SCHEMA` 暴露了(■-2) | 与本轮「图像生成」簇底稿交叉核对:确认 provider 层是否**只有** pet 一个非工具调用方 |
| H-R9B-3 | `tests/agent/test_pet_generate.py:14`:`pytestmark = pytest.mark.skipif(` | 覆盖 atlas 全流水线的 11 条用例默认整文件跳过,CI 常态不跑 | 查 `.github/workflows/**` 是否有任何地方设 `HERMES_RUN_SLOW_PET_TESTS=1`;本轮**未查**,标"未验证" |
| H-R9B-4 | `agent/pet/render.py:340`:`_ROWCOL_DIACRITICS: tuple[int, ...] = (` | 297 个码点的 kitty 变音符号表逐字抄进仓库,占 render.py 的 4.6% | 若做"外部规范内联"专题,可与其它抄表处(如 emoji 宽度表)并列;本轮未查是否有第二处 |
| H-R9B-5 | `agent/pet/store.py:218`:`while (pets_dir() / slug).exists():` | `unique_slug` 与 `register_local_pet` 之间是 TOCTOU:两次并发 hatch 同名概念会撞到同一个 slug | 未实测能否触发(需要两个并发 `/hatch`);标**推定**,不是已证缺陷 |
| H-R9B-6 | `tui_gateway/server.py:8225`:`_pet_cancelled: set[str] = set()` | 生成取消用一个模块级全局 set 存 token,未见清理策略 | 属网关簇,本轮只到边界为止;交给做 `tui_gateway` 的轮次 |

---

## 10. 可迁移的设计原则(给"自己造 harness"用)

1. **装饰性功能也要有三重关闭 + 零耦合面。** pet 默认关、未装宠物时自动无效、非 TTY 自动 off;
   全簇对主干只有 5 个 import 点。判断一个"可选功能"设计得好不好,看的是**删掉它要改几行主干**。
2. **把"活动 → 表现"的映射抽成一个无状态纯函数,并把优先序写进 docstring。**
   三个界面(Python CLI、Ink TUI、TypeScript 桌面)各自实现渲染,但共享同一份
   `derive_pet_state` 语义;TS 侧是照着这份 docstring 的优先序镜像实现的。
   **跨语言复用不了代码时,复用"被文档化的决策顺序"。**
3. **让模型做它擅长的(画),让确定性代码做它不擅长的(几何)。** 这是 `atlas.py` 的全部立论,
   也让整条生成流水线可以离线单测。
4. **能力探测宁可保守也不能阻塞。** `detect_terminal_graphics` 只读环境变量,
   显式放弃更准的 DA1 查询,理由是"绝不能挂住管道"。
5. **每条启发式规则旁边写清它修的是哪次翻车。** `atlas.py` 里几乎每个私有函数的 docstring
   都带一个具体故障(哈巴狗肚皮、Frogger 侧瓣、Gemini 地平线、被切掉的脚)。
   这让 1,183 行"魔法参数"变得可维护 —— 读者知道每个阈值为什么是那个数。
6. **信任边界要逐跳设,不能靠上游可信推下游。** 清单来自 HTTPS 的 petdex.dev,
   资产 URL 仍然逐条钉主机;一个 cosmetic 功能因此不会变成 SSRF 入口。

---

## 11. 延伸

- 成品章:`chapters/` 里本簇对应章(R9B 主线装订)。
- 相邻簇:图像生成 provider 层(`agent/image_gen_provider.py` / `agent/image_gen_registry.py` /
  `tools/image_generation_tool.py`)—— 本簇与它的接触面见 §3.1。
- 网关侧 16 个 `pet.*` RPC 在 `tui_gateway/methods_session.py:1326-1900`,属网关簇。
