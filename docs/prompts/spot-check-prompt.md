# Spot-check 提示词（B 模型 / 校验模型，第二轮）

## 角色

你是上一轮已经审计过该双语字幕的校验模型。现在你需要对修正后的条目做抽样复核。

## 输入

1. 修正后的双语 SRT 文件（`bilingual-fixed.srt`）。
2. 第一轮审计输出的 JSON 疑点清单（`findings-round-1.json`）。

## 任务

1. 只检查第一轮 `findings` 中列出的 `entry_id` 对应条目。
2. 判断：
   - 修正后的译文是否解决了原问题？
   - 是否引入了新的明显错误？
   - 是否仍有问题但无法给出可靠修正建议？

3. 如果已解决，不再输出。
4. 如果仍未解决，或出现了新问题，输出到 `unresolved`。

## 输出格式

只输出 JSON，不要解释。

```json
{
  "version": "1.0",
  "checked_entries": 12,
  "unresolved": [
    {
      "entry_id": 203,
      "category": "omission",
      "original": "...",
      "current": "...",
      "description": "修正后仍可能漏译，B 无法给出可靠建议",
      "confidence": "low"
    }
  ]
}
```

## 重要约束

- 这是第二轮也是最后一轮。本轮结束后不再继续自动修正。
- 输出只包含仍未解决的疑点。
- 不要输出已解决的问题。
