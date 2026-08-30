---
description: 执行 translanter 主工作流：本地视频 → 校对过的中文字幕 SRT。当用户要求处理/转写/翻译 video/ 下的视频时使用。
---

# 处理视频（translanter 主工作流）

权威流程文档：`docs/workflows/video-to-chinese-srt.md`（先完整读一遍再动手）。本 skill 是激活入口与编排清单。

## 输入确认

1. 视频文件在 `video/` 下；确认文件名与语种（语种已知则显式 `--language`，未知才自动检测）。
2. 中文视频只走转写（步骤 1），外语视频走全流程。
3. 工作区：`out/<视频名>/`（不含扩展名）。已存在且用户没说要重跑时，先问。

## 编排清单（主会话职责）

按流程文档执行，顺序：转写 → 重组 → 翻译 → 校验两轮 → unresolved.md。LLM 环节一律用 Agent 工具调 `.pi/agents/` 下的三个 subagent（subtitle-resegment / subtitle-translator / subtitle-auditor），**不要自己翻译或审计**。

主会话必须做的确定性工作（不信任 agent 自报）：

1. **转写后**：把 `--output_format all` 产出的 `<视频名>.srt/.json` 重命名为 `source.srt`/`source.json`。
2. **重组后**：程序校验——文本与词流逐字守恒、每条时间轴命中词边界、单调无重叠、≤12s。违规则 resume agent 修复。
3. **翻译/修正后**：校验条目数与时间轴 1:1；修正轮的改动条目号须与 findings 对应。合并双语 SRT。
4. **spot-check 后**：unresolved 与产物文件核对（防误报），再生成 `unresolved.md`。

## 环境细节（踩坑沉淀）

- bash 里 PATH 必须用 `/e/...` 形式（MSYS 转换），否则 CUDA DLL 加载失败且报错被吞。
- 每次转写前设 `HF_HOME="$PWD/.cache/huggingface"` 和 `PATH="$PWD/tools/cuda-libs:$PATH"`。
- 控制台输出含非 GBK 字符时用 `python -X utf8`。
