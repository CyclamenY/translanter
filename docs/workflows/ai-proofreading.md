# AI 校验环节执行步骤

> 对应 issue：#4「AI 校验环节的形态设计」
> 前置依赖：转写已产出 `source.srt`，翻译已产出初版 `translated.srt`。

## 目标

输入原文字幕与初译中文字幕，输出校对过的中文字幕，以及需要人工抽查的未解决疑点。

## 模型配置

- **A（翻译模型 / 执行修正）**：DeepSeek V4 Pro
- **B（校验模型 / 独立审计）**：Kimi k3

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

1. 打开 `docs/prompts/audit-prompt.md`。
2. 将提示词与 `bilingual.srt` 内容一起提交给 Kimi k3。
3. 保存返回的 JSON 为 `findings-round-1.json`。

### 步骤 3：执行修正（A 模型）

1. 打开 `docs/prompts/fix-prompt.md`。
2. 将提示词、`bilingual.srt` 与 `findings-round-1.json` 一起提交给 DeepSeek V4 Pro。
3. 保存返回的 SRT 为 `proofread.srt`。
4. 同时把 `proofread.srt` 与 `source.srt` 重新合并为 `bilingual-fixed.srt`。

### 步骤 4：第二轮 Spot-check（B 模型）

1. 打开 `docs/prompts/spot-check-prompt.md`。
2. 将提示词、`bilingual-fixed.srt` 与 `findings-round-1.json` 一起提交给 Kimi k3。
3. 保存返回的 JSON 为 `spot-check-result.json`。

### 步骤 5：生成人工抽查清单

将 `spot-check-result.json` 中的 `unresolved` 转换为 Markdown 表格 `unresolved.md`，格式参考 `docs/prompts/unresolved-template.md`（待补充）。

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
