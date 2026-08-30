# 翻译与校验环节 subagent 化，断句重组以词级时间戳为真源

端到端验证（#6）暴露了原设计的两个执行层问题：直接 curl 调 API 不可复现、无上下文管理；whisper 原生分段的碎句（11% 整句率）导致译文「半句一切」，达不到字幕要求。我们决定：翻译、修正、审计三个 LLM 环节固化为 pi custom subagent（`.pi/agents/`，模型与提示词绑定在 agent 定义里，主会话只做确定性编排与程序校验）；转写产出词级时间戳 JSON，新增断句重组步骤以词为最小单位重建分段，条目时间轴一律取自词边界，禁止估算插值。

## 已考虑的选项

- **重跑 whisper 调参数规避碎句**：实测关掉 word_timestamps 后整句率仅从 11% 升到 24%， whisper 原生分段按音频块切，不治本。否决。
- **「只合不拆」的重组**：可被程序完全校验，但无法处理源字幕偶发的超长单条（实测出现 23.9 秒条目），要么容忍要么估算时间戳。否决，改为以词级 JSON 为真源的可合可拆。
- **继续 curl / 手动聊天 UI 执行 LLM 环节**：无 prompt 固化、无模型绑定、不可复现。否决。
- **VideoCaptioner 等现成断句工具**：引入大依赖且断句逻辑与其翻译器耦合；subagent 方案与校验环节同架构，更一致。

## 后果

- 三个 subagent 定义入库（`.pi/agents/`），随仓库分发；模型绑定 deepseek/deepseek-v4-flash（thinking high）与 kimi-coding/k3-256。
- 每个视频一个工作目录 `out/<视频名>/`，标准文件名固定（source/resegmented/translated/bilingual/findings/proofread 等），环节间按名交接。
- 主会话承担程序校验职责：重组的文本守恒/词边界校验、翻译的条目数与时间轴 1:1 校验。不信任 agent 自报。
- 转写必须开 `--word_timestamps True` 并输出 JSON（幻觉三件套因此完整保留）。
- 长视频（>300 条）翻译分流到 LLM-Subtrans CLI，规则写在 translator agent 定义里。
- ADR 0001 的双模型架构不变，本文档只改变执行形态。
