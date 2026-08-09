# R9B · 多模态交付面

多模态交付面读完,表格锚点补上校验。

> 本轮范围以台账 `round=R9B` 为准。全部锚点针对基线
> `863e31318553cda8ad61df681d08175364d4164b`(下称 `863e313`)。

## 1. 开工先核范围

```verify
cd /home/user/hermes-study && awk -F'\t' 'NR>1{for(i=1;i<=6;i++) sub(/\r$/,"",$i); if($5=="R9B"){n++; l+=$3}} END{printf "%d 文件 / %d 行\n", n, l}' data/ledger.tsv
```

开工时读数 **46 文件 / 27,325 行**,与任务书给的数一致,无需修订。

本簇是**多模态交付面**:agent 怎么把结果交付给人、怎么接收人给的非文本输入。
按机制切六片派工,切分**逐文件核对过覆盖**(无遗漏、无重叠):

| 片 | 文件数 | 行数 | 内容 |
|---|---|---|---|
| A 图像生成与路由 | 6 | 3,581 | `agent/image_gen_provider.py`、`image_gen_registry.py`、`image_routing.py`、`tools/image_generation_tool.py`、`image_source.py`、`fal_common.py` |
| B 视频生成 | 5 | 2,756 | `agent/video_gen_provider.py`、`video_gen_registry.py`、`tools/video_generation_tool.py`、`flux3_video_tool.py`、`xai_video_tools.py` |
| C 语音合成 TTS | 7 | 5,345 | `agent/tts_provider.py`、`tts_registry.py`、`tools/tts_tool.py`、`tts_streaming.py`、`tts_text_normalize.py`、`neutts_synth.py`、`audio_container.py` |
| D 语音输入与唤醒 | 5 | 6,776 | `agent/transcription_provider.py`、`transcription_registry.py`、`tools/transcription_tools.py`、`voice_mode.py`、`wake_word.py` |
| E 视觉理解与终端呈现 | 12 | 5,214 | `tools/vision_tools.py`、`agent/display.py` 等 |
| F 虚拟宠物 pet | 11 | 3,653 | `agent/pet/` 全部 |
| **合计** | **46** | **27,325** | 与台账一字不差 |

## 2. 开工杂项:H-R9A-h 结清

*(正文见 §5.1。)*

## 3. 台账报数

*(收工填。)*

## 4. L1 全量 deep-read 的剩余判定(验收项 2)

## 5. 定案

## 6. 关卡读数

## 7. 测试(按 CLAUDE.md 连环境一起记)

## 8. 诚实申报

## 9. 移交清单
