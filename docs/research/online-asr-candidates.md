# 在线 ASR 服务候选调研（issue #22）

> 调研日期：2026 年 7 月（以本次网络检索到的公开页面为准）
> 目的：评估能否用在线 ASR 替代本地 faster-whisper + LLM 断句重组。筛选硬门槛：①支持中/英/日三语；②输出带时间戳（句级/段落级起步）；③有公开可自助注册的 API。
> 所有事实均来自本次搜索到的公开来源，逐条附链接；未查到的一律标注「未查到」。

## 1. 结论速览表

| 服务 | 中/英/日 | 时间戳 | 断句/标点 | 参考价格 | 免费额度 | 单文件限制 | 初步判断 |
|---|---|---|---|---|---|---|---|
| Deepgram Nova-3 | 三语均支持 | 词级 + utterance 级 | utterances=true 语义分段 + punctuate | $0.46/小时（PAYG） | $200 额度 | 异步大文件友好 | **推荐实测** |
| AssemblyAI Universal | 三语均支持 | 词级 + 句子级（/sentences） | 句子端点 + 自动标点 | $0.15–0.21/小时 | $50 额度 | 未查到严格上限 | **推荐实测** |
| 阿里云百炼（Qwen3-ASR / Fun-ASR / Paraformer） | 三语均有对应模型 | 句级 + 字级（默认开启） | 原生句级分段 + 标点 | ¥0.29–0.79/小时 | 10 小时/月 | 异步 2GB/12h，需公网 URL | **推荐实测** |
| 火山引擎豆包语音识别大模型 | 2.0 支持 13 语种含日/英 | 句级（utterance） | 内置智能分句、自动标点 | ¥0.8/小时 | 未查到 | ≤5 小时，URL 异步 | **推荐实测** |
| ElevenLabs Scribe v2 | 90+ 语种含中/日 | 词级 | 文本带标点，无句子分组字段 | $0.22/小时（批） | 免费额度（1 万 credits/月，主供 TTS） | 3GB | 可备选实测 |
| Mistral Voxtral Transcribe 2 | 13 语种含中/日 | 词级 | 未查到句子分组 | $0.18/小时 | 未查到 | 3h / 1GB | 可备选实测 |
| OpenAI（whisper-1 / gpt-4o 系） | 三语均支持 | 仅 whisper-1 有词/段级；gpt-4o-transcribe 无时间戳 | whisper 段切分不按句子 | $0.18–0.36/小时 | 无 | 25MB | 不解决断句问题，出局（字幕场景） |
| Groq（whisper-large-v3/turbo） | 三语均支持 | 段级 + 词级 | 同 whisper，非句子边界 | $0.04–0.111/小时 | 有（每日限额） | 25MB（免费）/100MB | 同上，分段问题依旧 |
| Google Cloud STT v2（Chirp 3） | 三语均支持 | 词级（官方警告 Chirp 3 词级时间戳可能降低准确率） | 自动标点，无句子分组 | $0.96/小时；动态批 $0.24/小时 | 60 分钟/月 | 批处理大文件 | 接入重，备选 |
| Azure AI Speech | 三语均支持，但日语无词级时间戳 | 词级（日语除外）+ 短语段 | 短语级分段 + 标点 | 实时 $1/小时，批 $0.36/小时 | F0 每月 5 小时 | 批处理大文件 | 日语缺词级时间戳，备选偏后 |
| Speechmatics（Ursa/Melia） | 55+ 语种含中/日 | 词级 | 自动标点，句分组未细查 | 约 $0.13–0.30+/小时（来源不一） | 每月免费时长（来源不一） | 批/实时均有 | 备选 |
| Gladia Solaria-1 | 100+ 语种含中/日 | 词级 | 未细查 | $0.61/小时起（Growth 低至 $0.20） | 有免费试用 | 未细查 | 备选 |
| 讯飞开放平台（录音文件转写） | 星火多语种大模型支持英/日等 13 语种 | 词级 + 标点同步预测 | 标点自动规整 | ¥4.9–9.9/小时（分档） | 有试用 | 500MB/5h | 备选 |
| 腾讯云 ASR | 15 语种含日语（标准引擎；大模型版以中英+方言为主） | 词级（ResTextFormat=2） | 自动标点、分句 | 极速版 ¥3.1/小时起（后付费首档） | 新用户 10h + 极速版 5h | ≤5 小时 | 备选 |
| 百度语音 | 中文/英语为主，日语仅见主题页 | 未查到明确说明 | 未查到 | 按次/时长包 | 有 | 异步 12h 内返回 | 信息不足，低优先 |

注：汇率粗按 $1≈¥7.1 换算感知价格；各页面价格随时间变动，实测前以官方定价页为准。

## 2. 逐家详情

### 2.1 OpenAI（whisper-1 / gpt-4o-transcribe / gpt-4o-mini-transcribe）

- **口碑定位**：whisper 是事实标准，但 gpt-4o-transcribe 在第三方基准中 WER 表现不佳（某对比中 44.58 WER，远差于 AssemblyAI/Deepgram/ElevenLabs，见 [AssemblyAI 博客](https://www.assemblyai.com/blog/the-top-free-speech-to-text-apis-and-open-source-engines)）；社区报告 gpt-4o 系存在语种强制不生效等 bug（[OpenAI 社区](https://community.openai.com/t/gpt-4o-transcribe-language-enforcement/1357014)）。
- **三语支持**：whisper-1 支持 98 种语言（含中/英/日）；新接口语言码支持 `zh-cn`/`zh-tw`/`cmn` 等中文区域码，日语未在文档页明确列出但 whisper 系列历来支持（[OpenAI 官方文档](https://developers.openai.com/api/docs/guides/speech-to-text)）。
- **时间戳**：`timestamp_granularities[]` **仅 whisper-1 支持**（词级/段级）；gpt-4o-transcribe / gpt-4o-mini-transcribe 不支持时间戳参数；`gpt-4o-transcribe-diarize` 返回带 start/end 的说话人分段（[同上文档](https://developers.openai.com/api/docs/guides/speech-to-text)）。
- **断句/标点**：whisper 的 segment 是约 10 秒级声学分块，**不按句子边界切**——这正是现状痛点；标点有，但分段无法省掉 LLM 重组。
- **价格**：whisper-1 与 gpt-4o-transcribe $0.006/分钟（$0.36/小时），gpt-4o-mini-transcribe $0.003/分钟（$0.18/小时），gpt-transcribe $0.0045/分钟，diarize $0.006/分钟（[costgoat](https://costgoat.com/pricing/openai-transcription)、[krea2turbo 汇总](https://krea2turbo.pro/blog/gpt-transcribe-vs-whisper-vs-gpt-4o-transcribe)，以官方为准）。无常驻免费额度（[spokenly](https://spokenly.app/blog/free-speech-to-text-apis)）。
- **限制**：单文件 25MB，超限需自行切片（[官方文档](https://developers.openai.com/api/docs/guides/speech-to-text)）。
- **API 形态**：REST，OpenAI SDK， multipart 上传，调用简单。
- **判断**：**出局**。能拿到时间戳的只有 whisper-1，分段问题与现状相同；gpt-4o 系干脆没时间戳。

### 2.2 Deepgram Nova-3

- **口碑定位**：第三方基准 WER 12.22，居中游（[AssemblyAI 对比](https://www.assemblyai.com/blog/how-accurate-speech-to-text)）；官方自我评价为低延迟生产首选（[Deepgram 博客](https://deepgram.com/learn/best-speech-to-text-apis)）。
- **三语支持**：Nova-3 支持简体中文（`zh`/`zh-CN`/`zh-Hans`）、繁中、粤语、日语（`ja`）；另有 `multi` 多语模式含日语但不含中文（[官方语言列表](https://developers.deepgram.com/docs/models-languages-overview)）。
- **时间戳**：词级 `words[]`（start/end/confidence）+ utterance 级（[utterances 文档](https://developers.deepgram.com/docs/utterances)）。
- **断句/标点**：`utterances=true` 把语音**切成语义单元**（每段带 start/end/transcript），配合 `punctuate=true` 每段文本带标点；官方称对「所有可用语言」开放（[同上](https://developers.deepgram.com/docs/utterances)）。`smart_format=true` 做数字/日期等可读性格式化（[opentranscription 模型档案](https://opentranscription.io/blog/deepgram-base-model-profile.html)）。
- **价格**：Nova-3 PAYG $0.0077/分钟（≈$0.46/小时），Growth 档 $0.0065/分钟；多语版促销价 $0.0048/分钟（[Deepgram 定价页](https://deepgram.com/pricing)、[brasstranscripts](https://brasstranscripts.com/blog/deepgram-pricing-per-minute-2025-real-time-vs-batch)）。
- **免费额度**：注册送 **$200 额度**，无需信用卡（[resourify](https://resourify.com/resources/deepgram)、[gladia 对比文](https://www.gladia.io/blog/deepgram-pricing)）。
- **限制**：预录音异步接口对大文件友好（未查到苛刻上限）。
- **API 形态**：REST（同步返回）+ WebSocket 流式 + 官方 SDK，可直传文件或传 URL，调用简单。
- **判断**：**推荐实测**。utterance 语义分段 + 词级时间戳 + 便宜 + 大额试用。

### 2.3 AssemblyAI（Universal-2 / Universal-3.5 Pro；Slam-1 已弃用）

- **口碑定位**：官方基准 Universal-3.5 Pro 平均 WER 7.69，领先 ElevenLabs Scribe v2（8.77）与 Deepgram Nova-3（12.22）（[AssemblyAI 官方博客](https://www.assemblyai.com/blog/the-top-free-speech-to-text-apis-and-open-source-engines)，注意为厂商自测）。
- **三语支持**：Universal-3.5 Pro 支持 18 语种，**含 Mandarin 和 Japanese**；Universal-2 支持 99+ 语种，日语在「High（≤10% WER）」档、中文在「Good（10–25% WER）」档；Streaming 多语版不含中/日（[官方模型参考](https://www.assemblyai.com/md/models)、[支持语言](https://www.assemblyai.com/docs/pre-recorded-audio/supported-languages)）。Slam-1 已标记弃用，官方建议迁移到 universal-3-5-pro（[官方定价](https://www.assemblyai.com/md/pricing)）。
- **时间戳**：词级（毫秒，官方称误差约 400ms 内）+ 句子级 `/sentences` 端点返回每句 start/end（[FAQ](https://assemblyai.com/docs/faq/does-your-api-return-timestamps-for-individual-words)）。
- **断句/标点**：自动标点 + 句子端点直接给句级分段；流式端基于标点做 end-of-turn 检测（[官方模型参考](https://www.assemblyai.com/md/models)）。
- **价格**：Universal-2 $0.15/小时，Universal-3.5 Pro $0.21/小时；流式 $0.15–0.45/小时（[官方定价](https://www.assemblyai.com/md/pricing)）。
- **免费额度**：注册送 **$50**（[同上](https://www.assemblyai.com/md/pricing)）。
- **API 形态**：REST 异步（上传→轮询）+ WebSocket 流式 + SDK；支持直接传文件，不强制对象存储。
- **判断**：**推荐实测**。句级分段现成、三语齐备、价格便宜；注意中文精度档位低于日语。

### 2.4 ElevenLabs Scribe（v2）

- **口碑定位**：WER 8.77，第三方榜单中仅次于 AssemblyAI（[AssemblyAI 对比](https://www.assemblyai.com/blog/the-top-free-speech-to-text-apis-and-open-source-engines)）；说话人分离准确率宣称 98%（[inworld 对比](https://inworld.ai/resources/best-speech-to-text-apis)）。
- **三语支持**：Scribe v2 支持 90+ 语种，官方文档明确列有 Japanese、Mandarin（[官方文档](https://elevenlabs.io/docs/overview/capabilities/speech-to-text)）。
- **时间戳**：精确词级时间戳（[官方定价页](https://elevenlabs.io/pricing/api)、[inworld](https://inworld.ai/resources/best-speech-to-text-apis)）。
- **断句/标点**：转写文本带标点，但未查到独立的句子分组字段——需要按标点+词时间戳自行聚句（未查到官方说明）。
- **价格**：批量 $0.22/小时，实时 $0.39/小时（[官方定价页](https://elevenlabs.io/pricing/api)）。
- **免费额度**：免费计划每月 10,000 credits（额度体系以 TTS 为主，STT 可用量未明确）（[bigvu 汇总](https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/)）。
- **限制**：单文件最大 3GB（[官方文档](https://elevenlabs.io/docs/overview/capabilities/speech-to-text)）。
- **API 形态**：REST（上传文件或 URL）+ Realtime WebSocket + SDK。
- **判断**：可备选实测。词级时间戳质量好，但句子边界要自己按标点聚。

### 2.5 Google Cloud Speech-to-Text v2（Chirp 3）

- **口碑定位**：企业级老牌，语种覆盖最广（Chirp 3 称 125+ 语言变体）（[transcribetube](https://www.transcribetube.com/blog/speech-to-text-api)、[ringly](https://www.ringly.io/blog/whisper-alternatives-for-ecommerce)）。
- **三语支持**：Chirp 3 有 24 个 GA 语种 + 77+ 预览语种（[openrouter 模型页](https://openrouter.ai/google/chirp-3)）；第三方 12 语种基准（含日语、普通话）覆盖了 Google STT v2（[koedesk 基准](https://koedesk.app/blog/stt-benchmark/)），中/英/日可用。
- **时间戳**：词级；但**官方文档警告 Chirp 3 开词级时间戳可能降低识别准确率**（[opentranscription 转述 Google 文档](https://opentranscription.io/blog/elevenlabs-scribe-v2.html)）。
- **断句/标点**：自动标点；未查到句子级分组字段。
- **价格**：v2 标准 $0.016/分钟（$0.96/小时）；动态批处理 $0.004/分钟（$0.24/小时，24h 内返回）；免费 60 分钟/月（[convertaudiototext](https://convertaudiototext.com/blog/speech-to-text-api-pricing-2026)、[getvoibe](https://www.getvoibe.com/resources/openai-whisper-alternatives/)）。
- **API 形态**：GCP 控制台 + 服务账号接入，REST/gRPC，批处理走 GCS，接入复杂度偏高（[transcribetube](https://www.transcribetube.com/blog/speech-to-text-api)）。
- **判断**：备选。价格偏高、接入重、Chirp 词级时间戳有官方警告。

### 2.6 Azure AI Speech

- **口碑定位**：企业级标准件，43 语种批量转写（[微软技术社区](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/choose-the-right-speech-and-voice-model/4533856)）。
- **三语支持**：中/英/日均在支持列表；但**日语不返回词级时间戳**（微软 Q&A 官方确认，[Microsoft Q&A](https://learn.microsoft.com/en-sg/answers/questions/2280752/speech-to-text-api-do-not-return-word-timestamps-f)）。
- **时间戳**：词级（`wordLevelTimestampsEnabled`，日语除外）+ 短语级分段（Display 文本带偏移）。
- **断句/标点**：批量转写按短语/句分段并带标点显示格式。
- **价格**：实时标准 $1/小时；批量 $0.36/小时（[brasstranscripts](https://brasstranscripts.com/blog/azure-speech-services-pricing-2025-microsoft-ecosystem-costs)）；F0 免费档每月 5 小时实时（[spokenly](https://spokenly.app/blog/free-speech-to-text-apis)）。
- **API 形态**：SDK/REST，批量转写需先上传 Blob 或提供公网 URL，异步任务制。
- **判断**：备选偏后。日语缺词级时间戳是硬伤；接入也偏重。

### 2.7 Groq（whisper-large-v3 / whisper-large-v3-turbo 托管）

- **口碑定位**：「最快的 whisper 托管」，large-v3 约 164 倍实时、turbo 约 216 倍实时（[LobeHub 汇总](https://lobehub.com/de/skills/jeremylongshore-claude-code-plugins-plus-skills-groq-core-workflow-b)）。
- **三语支持**：whisper large-v3 全系多语（含中/英/日，v3 新增粤语）（[theplanettools](https://theplanettools.ai/tools/whisper-large-v3)）。
- **时间戳**：`verbose_json` 返回 segment 级时间戳；传 `timestamp_granularities` 可得 words 词级数组（[第三方 Groq 指南](https://github.com/PocketLLM/PocketLLM/blob/feature/backend-api-dev/docs/groq-guide.md)、[9router issue 佐证](https://github.com/decolua/9router/issues/1034)）。
- **断句/标点**：与 whisper 原生一致——**segment 不按句子边界**，标点有但分段问题依旧。
- **价格**：large-v3 $0.111/小时，turbo $0.04/小时；最低计费 10 秒（[cloudzero](https://www.cloudzero.com/blog/groq-pricing/)、[Groq 指南](https://github.com/PocketLLM/PocketLLM/blob/feature/backend-api-dev/docs/groq-guide.md)）。
- **免费额度**：免费档每日 2,000 次请求、每小时 7,200 秒音频（[grizzlypeaksoftware](https://www.grizzlypeaksoftware.com/articles/p/groq-api-free-tier-limits-in-2026-what-you-actually-get-uwysd6mb)）。
- **限制**：免费档 25MB、dev 档 100MB（[Groq 文档](https://console.groq.com/docs/speech-to-text)）。
- **判断**：**出局**（针对本场景）。本质还是 whisper 分段，省不掉 LLM 重组；只适合作为廉价高速的 whisper 替代品。

### 2.8 Mistral Voxtral Transcribe 2（2026-02 新发布）

- **口碑定位**：FLEURS 上约 5.9% WER，优于 whisper large-v3 的 7.4%（厂商口径）（[ChatForest 评测](https://chatforest.com/reviews/mistral-voxtral-transcribe-2-realtime-asr-review/)）；第三方评价「价格低但语种有限」（[automateed](https://www.automateed.com/voxtral-transcribe-2-by-mistral-review)）。
- **三语支持**：13 语种：Dutch、English、French、German、Spanish、Portuguese、Italian、Russian、**Chinese**、Hindi、Arabic、**Japanese**、Korean（[Obsidian 论坛发布帖](https://forum.obsidian.md/t/voxtral-transcribe-dictate-and-type-at-the-same-time-into-your-notes-with-voice-commands-feedback-welcome/112674)）。
- **时间戳**：词级（每词 start/end），另带说话人分离（[ChatForest](https://chatforest.com/reviews/mistral-voxtral-transcribe-2-realtime-asr-review/)）。
- **断句/标点**：未查到句子级分组说明。
- **价格**：批量 $0.003/分钟（$0.18/小时），实时 $0.006/分钟（[ChatForest](https://chatforest.com/reviews/mistral-voxtral-transcribe-2-realtime-asr-review/)）。
- **限制**：单文件 3 小时 / 1GB（对比 OpenAI 的 25MB 宽松得多）（[hermes-agent issue](https://github.com/NousResearch/hermes-agent/issues/5887)）。
- **API 形态**：REST + Mistral SDK。
- **判断**：可备选实测。2026 年新服务，中日精度缺乏第三方验证。

### 2.9 Speechmatics（Ursa 2 / Melia-1）

- **口碑定位**：老牌企业级，55+ 语种；2026 年新模型 Melia-1 宣称 FLEURS 上胜过 Deepgram/微软/AssemblyAI（厂商自称，非独立结果）（[voxrater](https://voxrater.com/vendors/speechmatics/)）。
- **三语支持**：官方 AI 信息页语种表明确含 Mandarin、Cantonese、Japanese（[speechmatics.com/ai-info](https://www.speechmatics.com/ai-info)）。
- **时间戳/断句**：词级时间戳 + 自动标点（Enhanced/Standard 两档精度）；句子分组能力本次未细查。
- **价格**：公开来源分歧大——「from $0.30/小时」（[findapi](https://www.findapi.dev/api/speechmatics)）、「Melia-1 批 $0.24/小时」（[vexascribe](https://vexascribe.com/compare/best-transcription-api-for-developers)）、「低至 $0.129/小时 + 每月 10 免费小时」（[voxrater](https://voxrater.com/vendors/speechmatics/)）、「Enhanced 实时 $1.35/小时」（[vexascribe](https://vexascribe.com/compare/best-transcription-api-for-developers)）。注意其「用数据换折扣」策略（[dailyaifixs](https://dailyaifixs.com/blog/speechmatics-pricing-2026-the-training-discount-catch)）。
- **API 形态**：REST 批 + WebSocket 实时（[lablab](https://lablab.ai/tech/speechmatics/speechmatics-api)）。
- **判断**：备选。定价不透明、偏大客户销售。

### 2.10 Gladia（Solaria-1）

- **口碑定位**：从 whisper 起家的法国 STT 厂商，主打实时与多语（[TechCrunch](https://techcrunch.com/2023/06/19/gladia-turns-any-audio-into-text-in-near-real-time/)）；Solaria-1 覆盖 100+ 语种、原生 code-switching（[Gladia 博客](https://www.gladia.io/blog/code-switching-language-coverage-limitations)）。
- **三语支持**：100+ 语种，官方语种表含中文/日语（[Gladia 文档语种表](https://docs.gladia.io/chapters/language/supported-languages)）。
- **时间戳**：词级时间戳为标配功能（[Gladia 实时产品页](https://gladia.io/product/real-time)）；句子分组未细查。
- **价格**：Starter 异步 $0.61/小时、实时 $0.75/小时；Growth 低至异步 $0.20/小时（[同上](https://gladia.io/product/real-time)）。
- **API 形态**：REST 异步 + WebSocket 实时。
- **判断**：备选。起步价偏高。

### 2.11 阿里云百炼（Qwen3-ASR / Fun-ASR / Paraformer）

- **口碑定位**：国内中文识别第一梯队；Paraformer 在多个中文公开数据集 SOTA（[ModelScope 模型页转述](http://www.coreui.cn/news/260797.html)）；Fun-ASR 为 2025 年新一代端到端大模型，行业场景准确率提升 15%+（[通义官方公众号](http://mp.weixin.qq.com/s?__biz=MzUzNTkyNDg2NA==&mid=2247497406&idx=2&sn=4403232ff0b1332dfc4ce49f5d4a65d5)）。
- **三语支持**：
  - Qwen3-ASR 系列：字级时间戳明确支持中文、英语、日语（另含韩德法西意葡俄）（[百炼非实时识别文档](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)）。
  - Fun-ASR 主版本：中文七大方言 + 英语；**日语走 Fun-ASR-MTL**（31+ 语种，含日/韩/越/泰等）（[百炼 ASR 模型页](https://help.aliyun.com/zh/model-studio/asr-model/)、[fun-asr-mtl 模型信息](https://help.aliyun.com/zh/model-studio/fun-asr-mtl)）。
  - Paraformer-v2：中英为主（[第三方项目实测](https://github.com/weisi-gu/xiaoyuzhou-podcast-notes)）。
- **时间戳**：**句级 + 字级默认开启不可关闭**（`sentences[].begin_time/end_time` + `words[]`，毫秒）（[百炼非实时识别文档](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)、[实时识别文档](https://help.aliyun.com/zh/model-studio/real-time-speech-recognition-user-guide)）。
- **断句/标点**：原生句级分段；Fun-ASR 每个词还带 `punctuation` 字段（标点预测内建）（[同上](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)）。注意 Qwen3-ASR-Flash 走 OpenAI 兼容接口时不返回时间戳。
- **价格**：Paraformer-v2 0.00008 元/秒 ≈ **¥0.288/小时**，每月送 10 小时；Qwen3-ASR-Flash-Filetrans 0.00022 元/秒 ≈ **¥0.79/小时**，开通送 10 小时（90 天有效）（[第三方项目实测价目](https://github.com/weisi-gu/xiaoyuzhou-podcast-notes)；旧版 ISI 页亦列 Paraformer ¥0.288/小时，[阿里云计费页](https://help.aliyun.com/zh/isi/product-overview/billing-10)）。Fun-ASR 单价本次未查到，见[百炼定价页](https://help.aliyun.com/zh/model-studio/model-pricing)。
- **限制**：异步单文件 2GB / 12 小时；同步 Flash 系列 10MB / 5 分钟；说话人分离建议 ≤2 小时（[百炼非实时识别文档](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)）。
- **API 形态**：异步任务制，**只接受公网 URL**（官方推荐先传 OSS 生成 URL）；同步支持 Base64/本地路径（[同上](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide)）。
- **判断**：**推荐实测**。句级时间戳+标点原生输出、中文强项、便宜、有月免费额度；代价是 OSS 中转一步。

### 2.12 讯飞开放平台（录音文件转写 / 极速版）

- **口碑定位**：国内老牌，通用中文识别率宣称 98%（[讯飞社区](https://developer.xfyun.cn/thread/116150)）。
- **三语支持**：标准版默认中文普通话 + 英文；「星火多语种语音识别大模型」新增**日语**、韩语等 13 个语种，标点同步预测（[讯飞 lfasr 产品页](http://xfyun.cn/services/lfasr?ch=as12-78)）。
- **时间戳**：实时转写返回带时间戳的文字流（[rtasr 页](https://www.xfyun.cn/service/rtasr)）；录音转写结果含词级时间戳（[开发者实测描述](https://developer.cloud.tencent.com/article/2720933)为腾讯系，讯飞侧未单独查到粒度说明，极速版 FAQ 见 [fast_lfasr](https://www.xfyun.cn/services/fast_lfasr)）。
- **断句/标点**：中英混合、数字及标点自动规整（[fast_lfasr](https://www.xfyun.cn/services/fast_lfasr)）。
- **价格**：lfasr 分档 ¥9.9 / 8.8 / 5.9 / 4.9 每小时（按购买时长档位）（[讯飞定价页](https://www.xfyun.cn/service/lfasr)）。
- **限制**：500MB / 5 小时，16k 16bit 单声道 wav/pcm/m4a/mp3（[标准版文档](https://www.xfyun.cn/doc/asr/ifasr_new/API.html)）。
- **API 形态**：REST 上传 + 轮询；有 SDK。
- **判断**：备选。语种/标点能力够，但价格高于阿里/火山，接入资料相对陈旧。

### 2.13 火山引擎（豆包语音识别大模型）

- **口碑定位**：字节自研大模型，宣称较传统模型错误率降 30%，垂直领域降 50%+（[产品简介](https://www.volcengine.com/docs/6561/1354871)）。
- **三语支持**：豆包语音识别模型 2.0 新增日语、韩语、德语、法语等共 13 语种，中英保持高精度（[品玩报道](https://www.pingwest.com/w/309631)）；另支持多方言（[产品简介](https://www.volcengine.com/docs/6561/1354871)）。
- **时间戳**：句级 utterance 结果（流式文档说明「返回句级的识别结果」，[产品简介](https://www.volcengine.com/docs/6561/1354871?lang)）；大/小模型时间戳机制有专门说明（[大模型 HTTP 非流式接口](https://www.volcengine.com/docs/6561/1257584)）。
- **断句/标点**：**内置自动标点、语义顺滑、数字规整、智能分句，可任意搭配**（[产品简介](https://www.volcengine.com/docs/6561/1354871)）——与字幕需求高度对口。
- **价格**：豆包语音识别模型 2.0 录音文件识别 **¥0.8/小时**，流式 ¥1.0/小时（[火山引擎官网首页](https://www.volcengine.com/)）。
- **限制**：单文件 ≤5 小时；异步任务制，提交音频 URL 拿任务 ID 再查询（[录音文件识别标准版 HTTP](https://docs.volcengine.com/docs/6561/1354868)）。
- **API 形态**：HTTP 提交/查询两段式 + WebSocket 流式；需要 URL（可用自家 TOS 或任意公网地址）。
- **判断**：**推荐实测**。智能分句+标点内建、中日英齐备、价格便宜。

### 2.14 腾讯云 ASR

- **口碑定位**：中文社交口语数据积累深，中文实测字准 97.8%（[腾讯云开发者社区实测](https://developer.cloud.tencent.com/article/2720933)）。
- **三语支持**：整体支持 15 语种含**日语**、韩语、泰语等 + 31 种方言；普方英大模型主打中英+27 方言混识（[ccusoft 解析](https://www.ccusoft.com/post/16004.html)、[产品动态](https://cloud.tencent.com/document/product/1093/46797)）。日语主要挂在标准引擎，大模型版语种以中英方言为主（[录音文件识别请求文档](https://cloud.tencent.com/document/product/1093/37823)）。
- **时间戳**：`ResTextFormat=2` 返回词粒度详细结果（含词时间戳）（[同上](https://cloud.tencent.com/document/product/1093/37823)）；实时识别也支持词级时间戳用于字幕（[产品动态](https://cloud.tencent.com/document/product/1093/46797)）。
- **断句/标点**：结果按句分段、自动标点（[同上](https://cloud.tencent.com/document/product/1093/37823)）。
- **价格**：录音文件识别极速版后付费首档 **¥3.10/小时**（0–299 小时档，量阶梯递减）（[计费概述](https://cloud.tencent.com/document/product/1093/35686)）；新用户免费包：录音文件识别 10 小时 + 极速版 5 小时（[prompt.cn 教程](https://prompt.cn/sites/10595.html)）。
- **限制**：录音文件识别 ≤5 小时；极速版同步返回（30 分钟音频约 10 秒）（[极速版文档](https://cloud.tencent.com/document/product/1093/52097)）。
- **判断**：备选。价格比阿里/火山贵一个量级，日语不在大模型版主线。

### 2.15 百度语音（信息不足，低优先）

- 音频文件转写以中文普通话/英语为主，日语仅见主题页（[百度智能云主题页](https://cloud.baidu.com/theme/Y/1580040-48)）；批量转写 12 小时内返回（[产品页](https://ai.baidu.com/ai-doc/SPEECH/Tldjm0i4c)），时效性不适合本场景。时间戳粒度、断句能力本次未查到可靠公开说明。**暂不推荐。**

## 3. 建议进入实测的名单（最终选择权在用户）

按「断句/时间戳能力 × 三语质量 × 成本 × 接入难度」综合，建议实测 4 家（+1 备选）：

1. **Deepgram Nova-3**：`utterances=true` 语义分段 + 词级时间戳一次到位，三语官方支持，$200 免费额度够跑大量真实样本，REST 直传文件接入最简单。
2. **AssemblyAI Universal（2 / 3.5 Pro）**：`/sentences` 端点直接给句级分段 + 词级时间戳，$0.15–0.21/小时便宜，$50 免费额度；需顺带验证中文（Good 档）是否够用。
3. **阿里云百炼（Qwen3-ASR-Flash-Filetrans / Fun-ASR-MTL）**：句级+字级时间戳默认输出、标点内建，中文识别国内第一梯队，¥0.29–0.79/小时且每月 10 小时免费；代价是要先传 OSS 拿 URL。
4. **火山引擎豆包语音识别大模型**：官方明确「智能分句 + 自动标点」内建，2.0 支持 13 语种含日语，¥0.8/小时，中文语境（口语、混说）预期最强。
5. （备选）**ElevenLabs Scribe v2**：词级时间戳精度口碑好、多语 WER 榜前列，但没有句子分组字段，需自聚句——可作为「词级时间戳质量」的对照组。

明确出局的：**OpenAI gpt-4o 系**（无时间戳）与 **OpenAI whisper-1 / Groq**（whisper 分段不按句子，省不掉 LLM 重组，与现状无本质差异）；**Azure**（日语无词级时间戳）、**百度**（信息不足、批量时效差）暂不投入。

## 附：本次调研未覆盖/待办

- 各家的**中文口语混英文**（中英混说）实测 WER 均无独立第三方数据，需实测验证。
- 讯飞、腾讯、百度的日语文档资料陈旧，实测前需再确认当前可用性。
- 价格均为本次检索时点快照，实测前以官方定价页为准。
