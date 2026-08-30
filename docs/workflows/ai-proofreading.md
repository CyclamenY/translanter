# AI 校验环节执行步骤

> 对应 issue：#4「AI 校验环节的形态设计」
> 前置依赖：转写已产出 `source.srt`，断句重组已产出 `resegmented.srt`，翻译已产出初版 `translated.srt`。
> 执行形态（ADR 0002 起）：LLM 调用全部由 subagent 执行——修正用 `subtitle-translator`（形态 2），审计用 `subtitle-auditor`；提示词文件不变，仍是本环节的权威定义，agent 在运行时读取遵循。主会话只做合并、校验、清单生成等确定性工作。

## 目标

输入原文字幕与初译中文字幕，输出校对过的中文字幕，以及需要人工抽查的未解决疑点。

## 模型配置

- **A（翻译模型 / 执行修正）**：DeepSeek V4 Pro——subagent `subtitle-translator`（`.pi/agents/subtitle-translator.md`，模型 `deepseek/deepseek-v4-pro`）
- **B（校验模型 / 独立审计）**：Kimi k3——subagent `subtitle-auditor`（`.pi/agents/subtitle-auditor.md`，模型 `kimi-coding/k3-256`）
- 环境变量：`DEEPSEEK_API_KEY`、`KIMI_API_KEY`（Coding Plan key 即可）

> **安全提醒**：API key 只通过环境变量注入，不写入仓库任何文件，也不提交到 git。

## 输入

- `source.srt`：原文字幕
- `translated.srt`：A 模型初译的中文字幕
- `bilingual.srt`：合并后的双语字幕（格式见下文）

## 输出

- `proofread.srt`：已修正的中文字幕
- `findings-round-1.json`：第一轮疑点清单（B → A）
- `unresolved.md`：第二轮仍未解决、需人工扫读的疑点

## 双语 SRT 格式约定

每个标准 SRT 条目只显示一行译文， bilingual SRT 通过「条目内双行」表示原文与译文：

```
1
00:00:01,000 --> 00:00:04,000
Hello, world.
你好，世界。
```

规则：

- 原文在上，译文在下；
- 仍只显示一组时间轴；
- 不增加额外条目号。

你可以用任何文本编辑器或 Subtitle Edit 手动合并，也可用脚本做简单拼接。未来如流程固化，可补充一个现成的合并方法。

## 执行步骤

### 步骤 1：准备双语 SRT

将 `source.srt` 与 `translated.srt` 按条目号对齐，合并为 `bilingual.srt`。

### 步骤 2：第一轮审计（B 模型）

```
Agent(subagent_type="subtitle-auditor",
      prompt="任务形态：第一轮审计。遵循 docs/prompts/audit-prompt.md，审计 out/bilingual.srt，结果写入 out/findings-round-1.json")
```

### 步骤 3：执行修正（A 模型）

```
Agent(subagent_type="subtitle-translator",
      prompt="形态 2（执行修正）：读取 out/bilingual.srt 与 out/findings-round-1.json，产出 out/proofread.srt")
```

主会话校验：条目数与时间轴不变、改动条目号与 findings 一致（术语类疑点允许的连带条目除外）。然后把 `proofread.srt` 与源字幕重新合并为 `bilingual-fixed.srt`。

### 步骤 4：第二轮 Spot-check（B 模型）

```
Agent(subagent_type="subtitle-auditor",
      prompt="任务形态：第二轮 spot-check。遵循 docs/prompts/spot-check-prompt.md，复核 out/bilingual-fixed.srt 中 findings-round-1.json 列出的条目，结果写入 out/spot-check-result.json")
```

注意：spot-check 引用的译文可能与修正后文件不符（历史误报根因），未解决疑点须与产物文件核对后再交人工。

### 步骤 5：生成人工抽查清单

主会话将 `spot-check-result.json` 中的 `unresolved`（以及第一轮就判 unresolved、不经第二轮的疑点）转换为 Markdown 表格 `unresolved.md`，格式参考 `docs/prompts/unresolved-template.md`。

### 步骤 6：人工抽查（非必经）

操作者阅读 `unresolved.md`：

- 只判断中文是否通顺、自然；
- 不判断原文准确性；
- 如有修改，直接在 `proofread.srt` 中编辑对应条目。

## 结束条件

- `proofread.srt` 存在且为纯中文 SRT；
- `findings-round-1.json` 保存了第一轮审计记录；
- 如果存在未解决疑点，`unresolved.md` 已生成。

## 异常处理

- 如果 B 返回的 JSON 无法解析，检查提示词是否完整、SRT 是否过长（必要时按视频分段审计）。
- 如果两轮后未解决疑点过多，说明该视频翻译难度超出当前模型能力，建议人工分段处理或降级为纯人工校对。
