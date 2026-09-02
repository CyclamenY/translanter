# 主工作流：本地视频 → 校对过的中文字幕 SRT

> 对应 issue：#1（地图）、#6（端到端验证，2026-08-30 用 10 分钟英文技术视频实测通过）、#20（转写环节切换在线 Qwen3-ASR 的调研与实测地图，见 ADR 0003）
> 本文档是流程的唯一权威版本。各环节的实测耗时与踩坑记录见文末。

## 流程总览

```
本地视频文件
  → 1. 转写（Qwen3-ASR 在线，原生整句分段 + 词级时间戳）
  → 2. 翻译（subtitle-translator subagent / DeepSeek V4 Pro）
  → 3. AI 校验（subtitle-auditor subagent / Kimi k3，两轮封顶）
  → 4. 人工抽查（非必经，只判断中文通顺度）
  → proofread.srt（最终产物）
```

中文视频只走步骤 1（产出 `source.srt`）。烧录嵌入属后期范围。

> 2026-08-31 起转写环节从本地 faster-whisper 切换为在线 Qwen3-ASR（ADR 0003），
> 原步骤 2「LLM 断句重组」取消（在线模型整句率实测 100%）。
> 本地链（stable-ts 转写 + 重组）保留作回退，见文末「回退路径」。

## 环境基线（一次性安装）

| 组件 | 位置 | 说明 |
|---|---|---|
| Python venv | `venv/` | `python -m venv venv`，3.10+ |
| cloudflared | `tools/cloudflared.exe` | 音频公网 URL 中转（隧道）；[官方 release](https://github.com/cloudflare/cloudflared/releases) 下载 amd64 exe |
| 百炼 API key | 环境变量 | `DASHSCOPE_API_KEY`（阿里云百炼，开通「录音文件识别」） |
| 三个 subagent | `.pi/agents/` | subtitle-resegment / subtitle-translator / subtitle-auditor，已入库 |
| 翻译 key | 环境变量 | `DEEPSEEK_API_KEY`、`KIMI_API_KEY`（Kimi 用 Coding Plan key 即可，pi 内置 `kimi-coding` provider） |
| （回退）stable-ts | venv 内 | `venv/Scripts/pip install stable-ts`；仅回退路径需要 |
| （回退）CUDA DLL | `tools/cuda-libs/` | Purfview cuBLAS.and.cuDNN_CUDA12_win 压缩包解压（[来源](https://github.com/Purfview/whisper-standalone-win/releases/tag/libs)） |
| （回退）whisper 模型缓存 | `.cache/huggingface/` | 设 `HF_HOME` 指向项目内；large-v3 约 3GB |
| （回退/长视频翻译）LLM-Subtrans | `tools/llm-subtrans/` | `git clone` + `venv/Scripts/pip install -e tools/llm-subtrans` |

以上目录全部 gitignore，不入库。

## 工作区约定

**每个视频一个目录**：`out/<视频名>/`，文件名固定，全流程各环节按名读写：

| 文件 | 产生环节 | 内容 |
|---|---|---|
| `source.srt` / `source.json` | 1 转写 | 整句化原文字幕（>12s 已机械拆分） / 词级时间戳 |
| `translated.srt` | 2 翻译 | 初译中文字幕 |
| `bilingual.srt` | 3 前置 | 双语合并（审计输入） |
| `findings-round-1.json` | 3 审计 | 第一轮疑点清单 |
| `proofread.srt` | 3 修正 | **最终产物** |
| `bilingual-fixed.srt` / `spot-check-result.json` | 3 复核 | 第二轮输入 / 结果 |
| `unresolved.md` | 4 | 人工抽查清单 |

## 步骤 1：转写（Qwen3-ASR 在线）

```sh
# 需先设 DASHSCOPE_API_KEY（User 级环境变量即可）
venv/Scripts/python tools/transcribe_qwen.py <视频文件> --output-dir out/<视频名>
```

要点：

- 模型 `qwen-audio-3.0-asr-flash-filetrans`，异步任务制；实测三语种整句率 100%，原生整句分段，**无需再走断句重组**。
- 产出 `source.srt`（句内 ≥1s 静音处一律断条，字幕跟随语音节奏；仍 >12s 的片段按最大词间停顿机械拆完）与 `source.json`（whisper-ctranslate2 `--pretty_json` 兼容的词级时间戳结构）。
- 语种可自动检测（中/英/日实测均正确）；已知语种时建议显式传 `--language ja`（`language_hints`，最多 4 个代码，支持 zh/en/ja/ko 等 30 种，见 `--help`），可降低整句被误识别为其他语言的概率。
- 音频走公网 URL：脚本自动提取 16k 单声道音轨 → 本机起临时 HTTP 服务 → cloudflared 隧道中转（`--protocol http2`，与 TUN 代理共存；前提是把 `cloudflared.exe` 加入代理的进程直连规则，实测直连规则生效后隧道正常）。
- 限制：单文件 ≤12 小时 / 2GB（实测 3 小时视频云端约 6.5 分钟，¥2.4）；按时长计费 ¥0.79/小时。
- 已知特性：在线 ASR 有轻微运行间不确定性（同音频两次提交个别字词差异 <0.2%）。
- 专名提示词暂不支持（本地链的 `--initial-prompt` 无对应物）；专名错字交由下游审计环节兜底。

## 步骤 2：翻译

```
Agent(subagent_type="subtitle-translator",
      prompt="形态 1：工作区 out/<视频名>/，读取 source.srt 翻译成中文写入 translated.srt。视频背景：…")
```

- 给背景信息（题材、术语表）能显著提升专名一致性。
- **长视频分流**：>300 条时 agent 自动改用 LLM-Subtrans CLI（分块 + 错位重试 + 断点续翻）：
  `cd tools/llm-subtrans && ../../venv/Scripts/python scripts/deepseek-subtrans.py -l Chinese --project --postprocess -o <输出> <输入>`
- 主会话校验：条目数与时间轴和 source.srt 逐条相等。
- 合并双语 SRT（原文上、译文下，共享时间轴）为 `bilingual.srt`，供步骤 3。
- 注意：静音断条后部分条目是句中片段（不以句末标点收尾）；翻译时按上下文连贯处理即可（翻译 agent 整文件读入，理解不受断条影响）。

## 步骤 3：AI 校验（两轮封顶）

详见 [ai-proofreading.md](ai-proofreading.md)。双模型跨供应商：DeepSeek V4 Pro 翻译并执行修正，Kimi k3 独立审计并主导。执行方式已改为 subagent（`subtitle-translator` 形态 2 / `subtitle-auditor`），不再手动调 API。

## 步骤 4：人工抽查（非必经）

读 `unresolved.md`，只判断中文通顺度。实测中未解决疑点主要是 ASR 级疑点（转写本身错了，需对照音频确认）。

## 回退路径：本地 faster-whisper 链

断网、敏感素材或额度耗尽时回退（原步骤 1+2，详见 ADR 0003 与 git 历史）：

```sh
export HF_HOME="$PWD/.cache/huggingface"
export PATH="$PWD/tools/cuda-libs:$PATH"   # 注意：bash 里必须用 /e/... 形式，见踩坑 #2

venv/Scripts/python tools/transcribe_stable.py <视频文件> \
  --language <语种代码> --output-dir out/<视频名>
# 然后必须补 LLM 断句重组（whisper 原生分段仅 11–24% 整句率）：
# Agent(subagent_type="subtitle-resegment", prompt="工作区：out/<视频名>/。读取 source.srt 与 source.json，重组写入 resegmented.srt")
# 回退路径下翻译环节读 resegmented.srt 而非 source.srt
```

- 本地链调参定值与已知残留见 git 历史中文档版本（issue #19 四素材 A/B 实测）。
- 可选 `--initial-prompt "<题材/人名/术语>"` 降低专名错听；BGM 极重素材可叠 `--only-voice-freq` 或 `--denoiser demucs`。

## 实测耗时

新链（Qwen3-ASR，2026-08-30/31 实测）：

| 素材 | 时长 | 云端转写耗时 | 费用 |
|---|---|---|---|
| 中文麒麟9050 | 6 分 10 秒 | 约 21 秒 | ≈¥0.08 |
| 英文 mattpocock | 10 分 19 秒 | 首轮轮询即返回（<10 秒） | ≈¥0.14 |
| 日语雑談完整版 | 2 小时 58 分 | 6 分 26 秒 | ≈¥2.4 |

旧链参考（10 分 19 秒英文视频，RTX 3070）：转写 1 分 09 秒 + 断句重组约 10 分钟；翻译 3 分 19 秒；审计第一轮 1 分 53 秒；修正 1 分 13 秒；Spot-check 23 秒。翻译/校验环节不变。

## 踩坑记录（#6 实测）

1. `--hallucination_silence_threshold` 必须搭配 `--word_timestamps True`，否则 CLI 拒绝运行。
2. bash 里 PATH 用 `E:/...` 形式会导致 cublas64_12.dll 加载失败且**报错被吞**（输出目录为空）；必须用 `/e/...` 形式让 MSYS 转换。
3. 妙幕 SmartSub 确认无 CLI/headless（[issue #163](https://github.com/buxuku/SmartSub/issues/163) 开放中），CLI 场景用 LLM-Subtrans。
4. Kimi Coding Plan 的 key 与开放平台 key 是两套体系；前者走 `kimi-coding` provider（pi 内置），后者走 `api.moonshot.cn`。本流程用前者即可。
5. 审计模型做第二轮复核时可能引用 findings 里的历史译文而非修正后文件（误报根因）；`subtitle-auditor` 的内置纪律已修复此问题，主会话仍应对未解决疑点抽查核对。
6. 「只合不拆」的重组无法处理源字幕中的超长条目（whisper 偶发 20s+ 单条）；词级 JSON 使拆分有真实时间戳依据，严禁估算插值。
7. CUDA/float16 下 whisper 词级时间戳（DTW 对齐）存在随机抖动，弱语音/含混区可偏差数秒（实测日语素材多个 >5s 错位）。stable-ts 静音抑制把词边界重锁到真实语音边缘后大错位基本修复（能量裁决多数新版更准）；干净素材两版输出一致，无副作用。
