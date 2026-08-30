# translanter — Context

## 这个仓库是什么

一个**工作流仓库**，不是软件项目。目标：产出一套文档化的半自动流程，把本地视频文件变成带中文字幕的产物。不产生新软件；流程由现成工具（ffmpeg、whisper 实现、LLM API、字幕编辑器）拼接而成。

## Glossary

- **工作流 (the workflow)**：本仓库的核心交付物——一份文档化的、可重复执行的操作流程，输入本地视频文件，输出中文字幕。
- **转写 (transcription)**：从视频音轨生成带时间轴的原文文本（外语视频 → 外文字幕；中文视频 → 中文字幕）。机器完成，标准化工具为 whisper-ctranslate2（faster-whisper 实现）+ large-v3，产出 SRT 与词级时间戳 JSON。
- **断句重组 (resegmentation)**：把转写出的碎句字幕按完整句子重建分段。由 `subtitle-resegment` subagent 以词级时间戳 JSON 为真源执行（以词为最小单位可合可拆，时间轴取自词边界），主会话程序校验文本守恒与时间轴合法性。
- **翻译 (translation)**：把外文字幕翻译成中文字幕。由 LLM API 完成（whisper 自带的翻译只能译成英文，不可用）。
- **校验 (proofreading)**：翻译后的质量把关。由**校验模型**对照原文执行，主产物为**已修正中文字幕**与**疑点清单**；"对照原文的准确性"由 AI 负责，"中文是否通顺"仅由人抽查疑点清单，非必经。
- **翻译模型 (translation model)**：负责把外文字幕翻译成中文字幕的 LLM，受校验模型监督执行修正。
- **校验模型 (proofreading model)**：独立于翻译模型、负责审计译文质量的 LLM；其发现优先于翻译模型，操作者因可能不懂原文而无法复核其判断。
- **未解决疑点 (unresolved finding)**：经过两轮修正循环后，校验模型仍无法给出可靠修正建议、或翻译模型无法干净执行的疑点；最终以 Markdown 形式交人工判断中文通顺度，人不判断原文准确性。
- **软字幕 (soft subtitles)**：独立的字幕文件（如 .srt），与视频分离，可编辑、可开关。本流程的**规范产出格式是 SRT**。
- **硬字幕 / 烧录 (burned-in / hardsubs)**：字幕像素化压进视频画面。本项目的终态目标，但属于**后期范围**；接入时预期路线为 SRT → ASS（样式控制，尤其中外双语排版）→ ffmpeg 烧录。
- **说话人标签 (speaker label)**：多讲述者视频中标识"谁在说话"的占位符，规范形式为 A/B/C 自动编号；真名不由 AI 推断，由操作者在最终产物上自行填充。
- **人设 (persona)**：操作者可选择提供的、每个说话人标签一句的人物描述（身份、口吻、正式度），注入翻译环节以维持口吻一致；默认不提供，由翻译模型按标签自保持一致。
- **背景人声 (background speech)**：素材中需要剔除的非目标人声——典型为游戏录播中游戏角色/NPC 的语音，与要保留的真人实况语音可能在时间上重叠；区别于"带歌词的 BGM"（音乐场景）与多讲述者对话场景（所有人声都保留）。
- **目的地 (destination)**：当前 wayfinding 努力的终点——见 issue tracker 中 `wayfinder:map` 标签的地图 issue。当前有效目的地见[地图 #7](https://github.com/CyclamenY/translanter/issues/7)（多讲述者与复杂音源视频）；[地图 #1](https://github.com/CyclamenY/translanter/issues/1)（"产出校对过的中文字幕 SRT"）已达成。

## 环境基线（执行机器）

- Windows，RTX 3070 8GB（whisper large-v3 / fp16 可行）
- ffmpeg 已安装；Python 3.10 已安装
- 工具链已落地（全部在项目目录内、不入库）：`venv/`（whisper-ctranslate2 + llm-subtrans editable）、`tools/cuda-libs/`（CUDA 12 + cuDNN 9 DLL）、`tools/llm-subtrans/`、`.cache/huggingface/`（模型缓存）
- LLM 执行依赖 pi subagent：内置 provider `deepseek`（DEEPSEEK_API_KEY）与 `kimi-coding`（KIMI_API_KEY，Coding Plan key 可用）

## 范围约定

- 输入只认**本地视频文件**；视频怎么来的（下载、录制）不在流程内。
- **外语视频优先**：转写 + 翻译 + AI 校验。**中文视频**只做转写。
- 题材、语种、时长（几分钟到几小时）均不特化。
- 先自用；未来可能整理成给他人使用的版本（后期范围）。
