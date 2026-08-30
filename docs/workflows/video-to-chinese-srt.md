# 主工作流：本地视频 → 校对过的中文字幕 SRT

> 对应 issue：#1（地图）、#6（端到端验证，2026-08-30 用 10 分钟英文技术视频实测通过）
> 本文档是流程的唯一权威版本。各环节的实测耗时与踩坑记录见文末。

## 流程总览

```
本地视频文件
  → 1. 转写（stable-ts + faster-whisper，GPU）
  → 2. 断句重组（subtitle-resegment subagent，词级精度）
  → 3. 翻译（subtitle-translator subagent / DeepSeek V4 Pro）
  → 4. AI 校验（subtitle-auditor subagent / Kimi k3，两轮封顶）
  → 5. 人工抽查（非必经，只判断中文通顺度）
  → proofread.srt（最终产物）
```

中文视频只走步骤 1–2（转写 + 重组，产出 `resegmented.srt`）。烧录嵌入属后期范围。

## 环境基线（一次性安装）

| 组件 | 位置 | 说明 |
|---|---|---|
| Python venv | `venv/` | `python -m venv venv`，3.10+ |
| stable-ts | venv 内 | `venv/Scripts/pip install stable-ts`（带入 faster-whisper/torch）；whisper-ctranslate2 CLI 留作回退 |
| CUDA DLL | `tools/cuda-libs/` | Purfview cuBLAS.and.cuDNN_CUDA12_win 压缩包解压（[来源](https://github.com/Purfview/whisper-standalone-win/releases/tag/libs)） |
| whisper 模型缓存 | `.cache/huggingface/` | 设 `HF_HOME` 指向项目内；large-v3 约 3GB，首次运行自动下载 |
| LLM-Subtrans | `tools/llm-subtrans/` | `git clone` + `venv/Scripts/pip install -e tools/llm-subtrans`；仅长视频翻译用 |
| 三个 subagent | `.pi/agents/` | subtitle-resegment / subtitle-translator / subtitle-auditor，已入库 |
| API key | 环境变量 | `DEEPSEEK_API_KEY`、`KIMI_API_KEY`（Kimi 用 Coding Plan key 即可，pi 内置 `kimi-coding` provider） |

以上目录全部 gitignore，不入库。

## 工作区约定

**每个视频一个目录**：`out/<视频名>/`，文件名固定，全流程各环节按名读写：

| 文件 | 产生环节 | 内容 |
|---|---|---|
| `source.srt` / `source.json` | 1 转写 | 原文字幕 / 词级时间戳（重组真源） |
| `resegmented.srt` | 2 重组 | 整句化原文字幕 |
| `translated.srt` | 3 翻译 | 初译中文字幕 |
| `bilingual.srt` | 4 前置 | 双语合并（审计输入） |
| `findings-round-1.json` | 4 审计 | 第一轮疑点清单 |
| `proofread.srt` | 4 修正 | **最终产物** |
| `bilingual-fixed.srt` / `spot-check-result.json` | 4 复核 | 第二轮输入 / 结果 |
| `unresolved.md` | 5 | 人工抽查清单 |

## 步骤 1：转写

```sh
export HF_HOME="$PWD/.cache/huggingface"
export PATH="$PWD/tools/cuda-libs:$PATH"   # 注意：bash 里必须用 /e/... 形式，见踩坑 #2

venv/Scripts/python tools/transcribe_stable.py <视频文件> \
  --language <语种代码> --output-dir out/<视频名>
```

要点：

- 脚本用 faster-whisper（large-v3 / cuda / float16）转写，再由 stable-ts 做静音抑制，把词边界重锁到真实语音边缘——修复 CUDA 下 DTW 词时间戳的随机抖动（踩坑 #7）。
- **语种已知时显式 `--language`**，不要依赖自动检测（只看开头 30 秒）。
- 直接产出 `source.srt` 与 `source.json`（词级时间戳 JSON 是步骤 2 的真源），格式与 whisper-ctranslate2 `--pretty_json` 兼容，无需重命名。
- 幻觉四件套全开：`vad_filter`（解码前过滤静默/BGM，阈值 0.3）+ stable-ts VAD 词边界精修 + `condition_on_previous_text False` + `hallucination_silence_threshold 2`。
- 默认参数经 issue #19 四素材（日/中/英）A/B 实测定值：beam 8 / patience 2 / 掩码阈值 0.2 / `min_silence_dur 0.15` / `no_speech_threshold 0.7`。相比旧默认：漏听减少（实测语音覆盖最多 +46%）、幻觉循环可消除、专名错听减少。已知残留：VAD 重切分的窗口相位漂移可能引入单点误听（下游 LLM 校对可兜底的错误类别）。
- 可选 `--initial-prompt "<题材/人名/术语>"`：零成本降低专名错听，建议每视频提供（实测救回「おさらさん」「AI Coding Crash Course」等）。BGM 极重素材可再叠 `--only-voice-freq` 或 `--denoiser demucs`。
- 参数解析优先级：命令行 > `LANG_PRESETS` 语种预设 > `GLOBAL_DEFAULTS`（均在脚本顶部）。某语种实测出问题需要分化参数时，往 `LANG_PRESETS` 加该语种的覆盖键即可；每次运行的生效值与来源记录在 `run_meta.json`。
- 回退：whisper-ctranslate2 CLI（旧命令见 git 历史）。BGM 重的素材不要开 `--batched True`（会忽略幻觉参数）。

## 步骤 2：断句重组

whisper 原生分段按音频块切条，不管句子边界（实测仅 11–24% 条目以句末标点收尾），直接翻译会得到「半句一切」的字幕。此步把词流按完整句子重建分段：

```
Agent(subagent_type="subtitle-resegment",
      prompt="工作区：out/<视频名>/。读取 source.srt 与 source.json，重组写入 resegmented.srt")
```

- agent 规则：以词为最小单位既合又拆，时间轴一律取自词边界，文本一词不改，单条 ≤10 秒。
- **主会话程序校验**（必须执行，不信 agent 自报）：文本逐字守恒（与词流归一化后相等）、每条 start/end 命中词边界、单调无重叠、无 >12s 条目。
- 实测整句率从 11% 提升到 92%。

## 步骤 3：翻译

```
Agent(subagent_type="subtitle-translator",
      prompt="形态 1：工作区 out/<视频名>/，读取 resegmented.srt 翻译成中文写入 translated.srt。视频背景：…")
```

- 给背景信息（题材、术语表）能显著提升专名一致性。
- **长视频分流**：>300 条时 agent 自动改用 LLM-Subtrans CLI（分块 + 错位重试 + 断点续翻）：
  `cd tools/llm-subtrans && ../../venv/Scripts/python scripts/deepseek-subtrans.py -l Chinese --project --postprocess -o <输出> <输入>`
- 主会话校验：条目数与时间轴和 resegmented.srt 逐条相等。
- 合并双语 SRT（原文上、译文下，共享时间轴）为 `bilingual.srt`，供步骤 4。

## 步骤 4：AI 校验（两轮封顶）

详见 [ai-proofreading.md](ai-proofreading.md)。双模型跨供应商：DeepSeek V4 Pro 翻译并执行修正，Kimi k3 独立审计并主导。执行方式已改为 subagent（`subtitle-translator` 形态 2 / `subtitle-auditor`），不再手动调 API。

## 步骤 5：人工抽查（非必经）

读 `unresolved.md`，只判断中文通顺度。实测中未解决疑点主要是 ASR 级疑点（转写本身错了，需对照音频确认）。

## 实测耗时（10 分 19 秒英文视频，RTX 3070）

| 步骤 | 耗时 | 备注 |
|---|---|---|
| 转写 | 1 分 09 秒 | 模型已缓存；首次含 3GB 下载约 5 分钟 |
| 断句重组 | 约 10 分钟 | thinking max；138 条规模 |
| 翻译 | 3 分 19 秒 | DeepSeek V4 Pro |
| 审计第一轮 | 1 分 53 秒 | Kimi k3 |
| 修正 | 1 分 13 秒 | DeepSeek V4 Pro |
| Spot-check | 23 秒 | Kimi k3 |

## 踩坑记录（#6 实测）

1. `--hallucination_silence_threshold` 必须搭配 `--word_timestamps True`，否则 CLI 拒绝运行。
2. bash 里 PATH 用 `E:/...` 形式会导致 cublas64_12.dll 加载失败且**报错被吞**（输出目录为空）；必须用 `/e/...` 形式让 MSYS 转换。
3. 妙幕 SmartSub 确认无 CLI/headless（[issue #163](https://github.com/buxuku/SmartSub/issues/163) 开放中），CLI 场景用 LLM-Subtrans。
4. Kimi Coding Plan 的 key 与开放平台 key 是两套体系；前者走 `kimi-coding` provider（pi 内置），后者走 `api.moonshot.cn`。本流程用前者即可。
5. 审计模型做第二轮复核时可能引用 findings 里的历史译文而非修正后文件（误报根因）；`subtitle-auditor` 的内置纪律已修复此问题，主会话仍应对未解决疑点抽查核对。
6. 「只合不拆」的重组无法处理源字幕中的超长条目（whisper 偶发 20s+ 单条）；词级 JSON 使拆分有真实时间戳依据，严禁估算插值。
7. CUDA/float16 下 whisper 词级时间戳（DTW 对齐）存在随机抖动，弱语音/含混区可偏差数秒（实测日语素材多个 >5s 错位）。stable-ts 静音抑制把词边界重锁到真实语音边缘后大错位基本修复（能量裁决多数新版更准）；干净素材两版输出一致，无副作用。
