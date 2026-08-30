# 本地 Whisper 转写选型调研：实现、模型大小与安装方案

> 对应 issue：#2「转写选型：本地 whisper 实现、模型大小与安装方案」
> 调研日期：2026-08-30（覆盖各实现截至 2025–2026 年的状态）
> 问题：本工作流的转写步骤标准化用哪个本地 whisper 实现、哪个模型，在 Windows + Python 3.10 + RTX 3070 8GB 上如何安装运行；以及与妙幕 SmartSub 内置转写"合并 vs 分离"的取舍。
> 环境基线（已验证）：Windows，RTX 3070 8GB 显存，ffmpeg 已装，Python 3.10 已装，whisper 未装。

## 结论速览

**标准化方案：faster-whisper 实现 + `large-v3` 模型**，以独立 CLI 步骤运行（pip 装 `whisper-ctranslate2`，或免 Python 环境的 Purfview Faster-Whisper-XXL 独立 exe）。8GB 显存跑 large-v3 fp16 无压力（实测约 4.5–6GB），1 小时音频约 5–10 分钟。turbo 模型留作速度优先的备选，但粤语等语种上质量崩溃、长音频幻觉风险更高，不做默认。SmartSub 内置转写（whisper.cpp / faster-whisper 引擎，GPU 加速、应用内一键装运行时）作为**合并式替代**保留——见第 5 节的取舍结论。

---

## 1. 实现选择：openai-whisper vs faster-whisper vs whisper.cpp

### 1.1 faster-whisper（SYSTRAN/faster-whisper）—— 推荐

- **是什么**：用 CTranslate2 推理引擎重实现的 Whisper。官方 README 原话：同等精度下比 openai/whisper 快至 4 倍、显存更省；CPU/GPU 均支持 8-bit 量化进一步提速。
  来源：https://github.com/SYSTRAN/faster-whisper
- **3070 实测基准**：README 基准正是在 **RTX 3070 Ti 8GB + CUDA 12.4** 上跑的，与本机几乎同配置。13 分钟音频 + large-v2 模型：fp16 顺序解码 1m03s（约 12 倍实时），显存 4525MB；`batch_size=8` 时 17s（约 45 倍实时），显存 6090MB；int8 顺序 59s / 2926MB，int8 批处理 16s / 4500MB。8GB 显存全部配置可跑。
  来源：https://github.com/SYSTRAN/faster-whisper#benchmark
- **质量**：与 openai-whisper 同权重、同解码算法，精度等同（README："for the same accuracy"）。
- **长音频**：内置 Silero VAD（v1.2.1 起升级为 Silero-VAD V6），支持词级时间戳、批处理推理（`BatchedInferencePipeline`）、`hallucination_silence_threshold` 等长音频/幻觉缓解参数，被 Subtitle Edit、Buzz 等大量字幕工具采用。
  来源：https://github.com/SYSTRAN/faster-whisper/releases/tag/v1.2.1 ；https://github.com/SYSTRAN/faster-whisper#community-integrations
- **Windows + Python 3.10 安装摩擦**：低。`pip install faster-whisper` 即可（要求 Python ≥ 3.9）；音频解码走 PyAV（自带 ffmpeg 库），**不需要系统 ffmpeg**。GPU 运行需 CUDA 12 的 cuBLAS 和 cuDNN 9 的 DLL——Windows 上最简单的办法是从 Purfview 的 [whisper-standalone-win releases](https://github.com/Purfview/whisper-standalone-win/releases/tag/libs) 下载打包好的库压缩包，解压到 PATH 中的目录。
  来源：https://github.com/SYSTRAN/faster-whisper#requirements
- **维护状态**：活跃。最新 v1.2.1（2025-10-31），2025 年内发布 v1.1.0 / v1.1.1 / v1.2.0 / v1.2.1。
  来源：https://github.com/SYSTRAN/faster-whisper/releases
- **注意**：faster-whisper 本体是 Python 库不带 CLI。要命令行（直接出 SRT）用官方推荐的包装 **[whisper-ctranslate2](https://github.com/Softcatala/whisper-ctranslate2)**（与 openai-whisper CLI 参数兼容，`--output_format srt`；维护活跃，最新 0.5.7 / 2026-02-08），或 Purfview 的独立 exe（见 3.2）。
  来源：https://github.com/Softcatala/whisper-ctranslate2 ；https://pypi.org/project/whisper-ctranslate2/

### 1.2 openai-whisper（openai/whisper）—— 参考实现，不推荐做主用

- **是什么**：OpenAI 官方 PyTorch 参考实现，CLI 开箱即用（`whisper audio.mp4 --model large-v3 --output_format srt`）。
  来源：https://github.com/openai/whisper
- **缺点**：同精度下慢约 4 倍、显存占用更高（3070 Ti 基准：large-v2 fp16 需 2m23s / 4708MB，对比 faster-whisper 的 1m03s / 4525MB）；需要系统 ffmpeg 和 PyTorch（安装体积大）。
  来源：https://github.com/SYSTRAN/faster-whisper#benchmark
- **维护状态**：低频但未死。最新 PyPI 版本 20250625（2025-06，主要是 numpy 2 兼容）；上一个功能版 v20240930 引入了 large-v3-turbo。仓库未归档，但合并节奏很慢。
  来源：https://pypi.org/project/openai-whisper/ ；https://github.com/openai/whisper/releases/tag/v20250625
- **定位**：排查"是不是 faster-whisper 的 bug"时的对照组；不作为流程标准。

### 1.3 whisper.cpp（ggml-org/whisper.cpp）—— GPU 场景无明显优势

- **是什么**：C/C++ 移植（ggml 后端），2025 年起仓库迁至 ggml-org 组织。维护非常活跃：稳定版 v1.8.x（v1.8.7 / 2026-06-16），v1.9.x 预发布中（v1.9.3 / 2026-08-20）。Release 直接提供 Windows 预编译包，含 CUDA 版（`whisper-cublas-12.4.0-bin-x64.zip`），免编译。
  来源：https://github.com/ggml-org/whisper.cpp/releases
- **优势在 CPU/边缘端**（量化、Vulkan、CoreML 等）；在 NVIDIA GPU 上速度与 faster-whisper 同一量级（3070 Ti 基准：large-v2 fp16 + Flash Attention 1m05s，与 faster-whisper 的 1m03s 持平）。
  来源：https://github.com/SYSTRAN/faster-whisper#benchmark
- **对本流程的摩擦**：无官方 pip 包的概念、参数体系与 openai CLI 有差异、VAD 需单独下载 VAD 模型并显式开 `--vad`；模型要下 ggml 转换版。
  来源：https://github.com/ggml-org/whisper.cpp#voice-activity-detection-vad
- **定位**：SmartSub 的默认内置引擎就是 whisper.cpp（见第 5 节），所以走合并路线时会用到它；独立安装则没有必要。

### 1.4 其他值得一提的（2025–2026 现状）

- **WhisperX**（m-bain/whisperX）：faster-whisper + wav2vec2 对齐 + 说话人分离，访谈类内容需要区分说话人时有用，但依赖链重（pyannote），本流程暂未需要。
  来源：https://github.com/m-bain/whisperX
- **distil-whisper（distil-large-v3）**：只支持英文，本流程外语内容不限英语，不适用。
  来源：https://huggingface.co/distil-whisper/distil-large-v3
- **中文视频的备选赛道（非 whisper）**：FunASR 系的 SenseVoice-Small / FireRedASR 在中文 CER 上优于 whisper。FunASR 官方基准（184 个长音频、H100）：SenseVoice-Small CER 7.81%、169 倍实时，"for Chinese, FunASR is both faster and more accurate"。SmartSub 已内置 FunASR（sherpa-onnx 运行时）。**中文视频分支可考虑直接在 SmartSub 里用 FunASR 转写**，whisper 只负责外语——这是后续 issue 可以细化的问题。
  来源：https://www.funasr.com/en/blog/funasr-vs-whisper-benchmark.html ；https://smartsub.linxiaodong.com/features/subtitle-generation

## 2. 模型大小：8GB 显存怎么选

| 模型 | 参数量 | fp16 显存（3070 Ti 实测/估算） | 适用 |
| --- | --- | --- | --- |
| large-v3 | 1550M | 顺序约 4.5–5GB；批处理 8 约 6GB（同档 large-v2 实测 4525/6090MB） | **默认。多语种质量最高** |
| large-v3-turbo | 809M（解码器从 32 层砍到 4 层） | 比 v3 更小 | 速度优先时的备选 |
| medium 及以下 | ≤769M | 更小 | 8GB 显存没有降级理由，不选 |

显存来源：https://github.com/SYSTRAN/faster-whisper#benchmark ；turbo 结构来源：https://github.com/openai/whisper/discussions/2363

**turbo vs v3 的质量权衡（关键，按语种区分）**：2026 年 7 月 vocova 的 FLEURS 基准（large-v3 / turbo / small × 12 语种 × 每语种 50 句，CJK 用 CER）：

- 六种欧洲语言 turbo 只比 v3 差 0.3–1.4 个百分点；**日语 turbo 反而略优（5.8% vs 6.6% CER）**，韩语持平。
- **中文（普通话）turbo 略差：8.0% vs 6.7% CER**；**粤语 turbo 崩溃：43.3% vs 10.5% CER，不可用**；印地语差 6.6 个点。
- 抓到的 4 处教科书式重复循环幻觉全部来自 turbo 和 small，large-v3 一处没有。
- 速度收益：turbo 约比 v3 快 1.4 倍。

来源：https://vocova.app/blog/ai-transcription-accuracy-benchmark-2026

**结论**：本流程内容异构（访谈/纪录片/VTuber，可能小语种），且后面有 LLM 翻译 + AI 校验兜底小错，但幻觉循环会污染整段时间轴、校验也难救——**默认 large-v3**。明确是日/韩/欧洲语言且追求速度时才用 turbo；中文（尤其粤语）素材不要用 turbo。`compute_type` 默认 `float16`，爆显存时退 `int8_float16`（README 基准显示 int8 几乎不掉速不掉点）。

## 3. 安装与运行（Windows + Python 3.10 + RTX 3070）

### 3.1 路径 A：pip 安装 whisper-ctranslate2（标准命令行）

```powershell
# 1) 安装 CLI（自动带入 faster-whisper / ctranslate2；要求 Python>=3.9，3.10 满足）
pip install whisper-ctranslate2

# 2) GPU 库：下载 Purfview 打包的 cuBLAS/cuDNN DLL
#    https://github.com/Purfview/whisper-standalone-win/releases/tag/libs
#    解压到某目录并加入 PATH（最新 ctranslate2 需要 CUDA 12 + cuDNN 9 版本的库）
#    来源：https://github.com/SYSTRAN/faster-whisper#requirements

# 3) 转写：外语视频（已知语种就显式指定，例：日语）
whisper-ctranslate2 input.mp4 --model large-v3 --language ja --output_format srt --output_dir . --device cuda --compute_type float16 --vad_filter True

# 4) 中文视频
whisper-ctranslate2 input.mp4 --model large-v3 --language zh --output_format srt --output_dir . --vad_filter True
```

要点：

- **语种检测 vs 显式指定**：不显式给 `--language` 时会自动检测（faster-whisper 会报告检测到的语种及概率），但自动检测只看开头约 30 秒，VTuber 开场 BGM/无声易导致误判。**内容语种已知时一律显式 `--language`**；只有完全未知的素材才依赖自动检测并人工确认。
  来源：https://github.com/SYSTRAN/faster-whisper#usage
- **VAD**：`--vad_filter True` 启用 Silero VAD 剔除无语音段，长音频（多小时）必开，既提速又抑制静默段幻觉。可调 `--vad_min_speech_duration_ms` / `--vad_max_speech_duration_s` 等。
  来源：https://github.com/Softcatala/whisper-ctranslate2#using-voice-activity-detection-vad-filter
- **吞吐估算（3070 8GB，按 README 同档基准外推）**：large-v3 fp16 顺序解码约 10–13 倍实时（1 小时音频约 5–6 分钟）；批处理模式可到 40 倍以上。turbo 再快约 1.4 倍。
  来源：https://github.com/SYSTRAN/faster-whisper#benchmark ；https://vocova.app/blog/ai-transcription-accuracy-benchmark-2026
- 模型首次运行自动从 HuggingFace（Systran 组织）下载 CTranslate2 转换版（large-v3 约 3GB），之后离线可用。
  来源：https://github.com/SYSTRAN/faster-whisper#model-conversion

### 3.2 路径 B：Purfview Faster-Whisper-XXL（免 Python 环境的等价物）

不想维护 Python 环境时，用 [Purfview/whisper-standalone-win](https://github.com/Purfview/whisper-standalone-win) 的 **Faster-Whisper-XXL**——faster-whisper 的独立 Windows exe，检测到 CUDA 自动用 GPU，参数体系与 whisper-ctranslate2 基本相同，持续更新（2025-11 仍在发版）。faster-whisper 官方 README 亦收录该项目。

```powershell
faster-whisper-xxl.exe input.mp4 --language ja --model large-v3 --output_format srt --output_dir source --vad_filter True
```

来源：https://github.com/Purfview/whisper-standalone-win ；https://github.com/SYSTRAN/faster-whisper#requirements

代价：社区单维护者 repack（Pro 版捐赠墙），供应链信任度低于 pip 官方包；流程文档把它作为"零安装摩擦"备选而非首选。

## 4. 已知坑：幻觉与重复循环（VTuber / BGM 场景）

Whisper 系模型在**静默段、纯音乐段、 crowd noise** 上容易产生幻觉字幕（编造文本或无限重复同一句），VTuber 直播（BGM + 哼唱 + 长静默）是高危场景。2026 年的多语种基准实测也确认：抓到的重复循环幻觉全部来自 turbo/small，且"smaller models do not fail gracefully"。
来源：https://vocova.app/blog/ai-transcription-accuracy-benchmark-2026

缓解手段（faster-whisper / whisper-ctranslate2 均支持）：

| 手段 | 参数 | 说明 |
| --- | --- | --- |
| VAD 预过滤 | `--vad_filter True` | 转写前剔除静默/非语音段，是第一道也是最重要的一道 |
| 关闭上文条件 | `--condition_on_previous_text False` | 幻觉文本不再作为下文 prompt，打断重复循环的链式放大 |
| 幻觉静默跳段 | `--hallucination_silence_threshold 2`（秒） | 检测到疑似幻觉时跳过其周围的静默段，避免时间轴被幻觉句钉死（faster-whisper PR #646 引入） |
| 质量阈值回退 | `logprob_threshold` / `no_speech_threshold` / `compression_ratio_threshold`（默认值即可） | 低置信/高压缩比段触发温度回退重采样或弃段 |
| 模型选择 | 用 large-v3 而非 turbo/small | 见第 2 节；大模型幻觉率实测更低 |

来源：https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py ；https://github.com/SYSTRAN/faster-whisper/pull/646 ；https://github.com/Softcatala/whisper-ctranslate2#ctransslate2-specific-options

注意两点：

- **批处理模式（`--batched True`）会忽略** `compression_ratio_threshold` / `logprob_threshold` / `no_speech_threshold` / `condition_on_previous_text` / `hallucination_silence_threshold` 等参数。**BGM 重、幻觉敏感的素材不要用批处理模式**，宁可用顺序解码换可控性；干净访谈素材才开批处理追速度。
  来源：https://github.com/Softcatala/whisper-ctranslate2#batched-inference
- **温度回退带随机性**：同一文件两次跑可能产出不同文本（触发回退时随机采样）。需要严格可复现的对比测试时注意；日常流程无碍。
  来源：https://github.com/Softcatala/whisper-ctranslate2/blob/master/FAQ.md

## 5. 合并 vs 分离：SmartSub 内置转写 vs 独立 CLI

姊妹调研（#3，docs/research/srt-llm-translation.md）已确定翻译步骤用妙幕 SmartSub。SmartSub 本身内置完整转写能力：默认引擎 whisper.cpp（应用内一键下载 CUDA 加速包，无需装 CUDA Toolkit），另可按需装 **faster-whisper 自包含运行时**（独立于系统 Python，应用内下载，支持 GPU、词级时间戳、多镜像源模型下载），还有 FunASR/Qwen3-ASR 等中文优化引擎。
来源：https://smartsub.linxiaodong.com/features/subtitle-generation ；https://smartsub.linxiaodong.com/guides/engines/faster-whisper ；https://smartsub.linxiaodong.com/advanced/hardware-acceleration ；https://smartsub.linxiaodong.com/guides/engines/models

| 维度 | 合并（SmartSub 内置转写） | 分离（独立 faster-whisper CLI） |
| --- | --- | --- |
| 环境维护 | **零**：运行时/加速包/模型全在应用内装 | 一次性装 Python 包 + CUDA DLL（或用 XXL exe 免去） |
| 步骤衔接 | 转写→翻译→校对同一界面，产物零搬运 | 转写出 SRT 后再导入 SmartSub 翻译，多一步文件交接 |
| 参数可控性 | 暴露常用项（模型、设备、VAD、词级时间戳），细粒度幻觉参数未必全暴露 | **完整**：`condition_on_previous_text`、`hallucination_silence_threshold`、VAD 细参、compute_type 全部可控可文档化 |
| 可复现性 | 行为随 SmartSub 版本变化，命令不可引用 | **固定命令行**，流程文档可直接引用、可逐字复跑 |
| 故障定位 | 转写问题与翻译问题耦合在同一应用内排查 | 每步产物独立（SRT 落盘），可单独重跑/抽查/换工具 |
| 中文视频分支 | **有加分**：可直接切 FunASR/SenseVoice（中文 CER 优于 whisper） | whisper 中文够用但非最优 |
| 供应链/锁定 | 依赖单一应用的行为与更新节奏 | pip 官方包，可换 XXL exe 等价物 |

**取舍判断**：分离路线的核心价值是（a）幻觉缓解参数完整可控——对本流程最高危的 VTuber/BGM 场景（第 4 节）直接相关；（b）流程文档以固定命令行为准，可审计、可复现；（c）转写产物独立落盘，翻译/校验步骤出问题不用回转写。合并路线的核心价值是省事和中文引擎。一次性的环境安装成本在流程生命周期内可忽略。

## 推荐方案

**标准实现**：faster-whisper，经独立 CLI 运行（分离式）。

**标准模型**：`large-v3`（`compute_type float16`）。turbo 仅在确认素材为日/韩/欧洲语言且赶时间时使用；中文（含粤语）素材不用 turbo。中文视频如 whisper 效果不佳，后续可用 SmartSub 内置 FunASR 另立分支。

**安装与运行（一次性 + 每次）**：

```powershell
# 一次性安装
pip install whisper-ctranslate2
# + 下载 https://github.com/Purfview/whisper-standalone-win/releases/tag/libs 的 CUDA 12 / cuDNN 9 库，
#   解压并把目录加入 PATH（GPU 必需）
# 免 Python 替代：Purfview Faster-Whisper-XXL 独立 exe（https://github.com/Purfview/whisper-standalone-win）

# 标准转写命令（外语视频，语种已知；以日语为例）
whisper-ctranslate2 input.mp4 --model large-v3 --language ja --output_format srt --output_dir . --device cuda --compute_type float16 --vad_filter True --condition_on_previous_text False --hallucination_silence_threshold 2

# 中文视频
whisper-ctranslate2 input.mp4 --model large-v3 --language zh --output_format srt --output_dir . --vad_filter True --condition_on_previous_text False --hallucination_silence_threshold 2

# 干净访谈素材追速度（幻觉敏感素材禁用批处理）
whisper-ctranslate2 input.mp4 --model large-v3 --language ja --output_format srt --output_dir . --batched True
```

产出的原文 SRT 交给 SmartSub 做 LLM 翻译 + 校对（见 docs/research/srt-llm-translation.md）。

**合并 vs 分离结论**：**分离为主**——独立 CLI 转写是流程的标准步骤，SmartSub 只做翻译/校对。**合并为备**——临时任务、不想装环境、或中文视频想用 FunASR 引擎时，允许直接在 SmartSub 内完成转写（其 faster-whisper / whisper.cpp 引擎与标准方案同源，质量无本质差异），但流程文档的基准行为、参数调优和故障排查一律以独立 CLI 命令为准。

## 遗留问题（后续 issue 候选）

- 中文视频分支是否整体改走 FunASR/SenseVoice（SmartSub 内置），需要实测对比 whisper large-v3 在真实素材上的中文 CER。
- 访谈类素材是否需要说话人分离（WhisperX / whisper-ctranslate2 `--hf_token` diarization）。
- 用 2–3 段真实素材（含一段 VTuber 直播）回归验证上述命令的时间轴质量与幻觉抑制效果。
