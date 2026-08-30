# 研究：带歌词 BGM 场景下的对话人声剥离（issue #9）

> 问题：视频人声对话叠加在**带歌词的背景音乐**上时，whisper 会把 BGM 歌词也转写进字幕。如何在转写前剥掉 BGM（含歌声），只留对话人声？
>
> 环境约束：Windows 10/11，RTX 3070 8GB VRAM，Python 3.10 venv，ffmpeg 已装；只用现成开源工具。

---

## 结论 / 推荐（TL;DR）

**核心发现：音源分离解决不了"BGM 歌声"这一半问题。** demucs/UVR 的 vocals 轨定义是"歌曲中的全部人声"（主唱+伴唱），说话声和唱歌声在模型眼里都是 vocals。分离能干净剥掉乐器伴奏，但 BGM 里的歌声会和对白一起留在 vocals 轨。因此：

1. **分情况处理（推荐主路线）**：
   - **BGM 是纯音乐（无歌声）**：直接用 **demucs** `htdemucs` / `htdemucs_ft` 的 `--two-stems=vocals` 分离，vocals 轨喂 whisper。这是成熟、官方支持 Windows、MIT 许可、8GB VRAM 充裕的方案。
   - **BGM 含歌声（真正的问题场景）**：分离无法区分说话与唱歌。改用**时序路线**：用 **inaSpeechSegmenter** 做 speech/music 区段检测，只在 speech 区段转写；对"对话与歌声重叠"的区段再做分离提取 vocals 后单独转写。whisper 层面继续用已有的 VAD + 幻觉三件套，并加 `condition_on_previous_text=False`。
2. **不要把长音频的分离人声轨直接整段替换原音频喂 whisper**：论文实测这种做法在长音频上反而显著降低转写质量（见 §3b）。分离轨更适合用作"哪里有人声"的检测信号，而不是转写输入本身。
3. **备选**：需要 karaoke（主/伴唱分离）、去混响等 UVR 模型时，用 **audio-separator**（MIT，pip 安装，CLI + Python API，自动下载 UVR 模型库）——UVR 本体是 GUI-only、无官方 CLI，与"妙幕无 CLI"同类教训，不要集成 UVR GUI。
4. **不推荐**：spleeter（2019 年后停更，质量明显落后）。

---

## 1. 背景

whisper 在 BGM 叠加人声的音频上的失败模式是公开记录的已知问题：转写出背景歌词、凭空幻觉出文本、或丢弃语音（[openai/whisper Discussions #1873](https://github.com/openai/whisper/discussions/1873)、[#679](https://github.com/openai/whisper/discussions/679)；[Filmroom issue #9](https://github.com/nethum529/Filmroom/issues/9) 明确描述了短视频场景"BGM 叠加人声 → whisper 转写出歌词/幻觉/丢语音"）。纯音乐段落还会触发典型的非语音幻觉（[MetaWhisp: Why Whisper Hallucinates](https://metawhisp.com/blog/whisper-hallucination-silence-fix/)）。

## 2. 候选方案盘点

### 2.1 demucs（Meta / facebookresearch）★ 主选

- 仓库：https://github.com/facebookresearch/demucs （论文：Hybrid Spectrogram and Waveform Source Separation, Rouard et al.）
- **CLI**：官方一等公民。`demucs --two-stems=vocals -n htdemucs_ft input.wav`。`--two-stems=vocals` 只输出 vocals + no_vocals 两轨（[README](https://github.com/facebookresearch/demucs)；[issue #511](https://github.com/facebookresearch/demucs/issues/511) 说明 two-stems 只是合并保存其余轨）。
- **模型变体**：`htdemucs`（默认单模型）、`htdemucs_ft`（4 个微调模型的 BagOfModels，质量更好但约 4 倍耗时）、`htdemucs_6s`（多 guitar/piano 轨）、`hdemucs_mmi`（v3 重训基线）（[DeepWiki: Models and Variants](https://deepwiki.com/facebookresearch/demucs/5.1-models-and-variants)）。v3 时代的 `mdx`/`mdx_extra` 等 BagOfModels 仍可用。
- **质量**：htdemucs_ft vocals SDR ≈ 9.2 dB（MUSDB18-HQ 中位数），对比 spleeter 6.9 dB（[demucs-onnx comparison](https://stemsplit.github.io/demucs-onnx/comparison/)）。
- **Windows**：官方文档 [docs/windows.md](https://github.com/facebookresearch/demucs/blob/main/docs/windows.md)："NVIDIA 显卡显存超过 2GiB 即可 GPU 加速"，装 CUDA 版 PyTorch 即可。8GB 对 demucs 很充裕。
- **速度**：GPU 上远快于实时——ONNX 导出版在 T4 上 3 分钟歌曲约 5 秒（[stemsplit.io](https://stemsplit.io/blog/htdemucs-ft-onnx-export)）；PyTorch 原版略慢但同量级。CPU 上 v4 模型约为音频时长的 3 倍（[issue #426](https://github.com/facebookresearch/demucs/issues/426)，含 `--segment` 提速/省显存说明）。HTDemucs 架构上限 segment 7.8 秒（[DeepWiki](https://deepwiki.com/facebookresearch/demucs/5.1-models-and-variants)）。
- **许可证**：代码 MIT（[LICENSE](https://github.com/facebookresearch/demucs/blob/main/LICENSE)）。**注意坑**：模型权重历史上按 MUSDB 数据集条款"仅供研究用途"（作者在 issue #267/#327/#508 中的表态）；2026 年官方 HF 镜像 [adefossez/HTDemucs](https://huggingface.co/adefossez/HTDemucs/discussions/1) 标了 MIT，但被问及是否刻意为之，尚无定论。本仓库是本地个人工作流，风险低，但值得知晓。

### 2.2 Ultimate Vocal Remover（UVR）——GUI-only，本体不推荐，模型生态可复用

- 仓库：https://github.com/Anjok07/ultimatevocalremovergui ，MIT 许可（[README](https://github.com/Anjok07/ultimatevocalremovergui)），但**是 tkinter GUI 应用，无官方 CLI/headless 模式**，且项目 2023 年 v5.6 后基本停更。与"妙幕 SmartSub 无 CLI"同类教训：**不要试图自动化 GUI**。
- 第三方 CLI 封装存在但小众/维护性存疑：[seanghay/uvr](https://github.com/seanghay/uvr)、[hiroaki222/uvr-headless](https://github.com/hiroaki222/uvr-headless)（fork 掉 GUI 的封装）、PyPI [uvr-headless-runner](https://pypi.org/project/uvr-headless-runner/)（2026-02 发布）。
- **真正的价值在模型生态**：UVR 训练的 MDX-NET / VR / Karaoke / De-Reverb 系列模型是社区标准，且有专门的 **Karaoke 模型**（UVR-MDX-NET Karaoke 2、5_HP-Karaoke-UVR）做"主唱 vs 伴唱"二级分离（[UVR Discussion #1096](https://github.com/Anjok07/ultimatevocalremovergui/discussions/1096)、[#1250](https://github.com/Anjok07/ultimatevocalremovergui/discussions/1250)），以及 De-Echo/De-Reverb 模型处理混响（[UVR issue #469](https://github.com/Anjok07/ultimatevocalremovergui/issues/469)）。

### 2.3 audio-separator（nomadkaraoke/python-audio-separator）★ 备选（UVR 模型的 CLI 入口）

- 仓库：https://github.com/nomadkaraoke/python-audio-separator ，**MIT**（[LICENSE](https://github.com/nomadkaraoke/python-audio-separator/blob/main/LICENSE)），持续活跃维护（PyPI 0.44.x，2026 年仍在发版）。
- 定位：把 UVR 的模型库封装成 `pip install audio-separator` 后可直接用的 **CLI + Python API**，支持 MDX（ONNX）、VR、Demucs v4、MDXC/RoFormer 架构，自动下载 70+ 预训练模型（含 karaoke、de-reverb、MDX23C、BS/MelBand RoFormer）（[PyPI](https://pypi.org/project/audio-separator/)、[DeepWiki](https://deepwiki.com/nomadkaraoke/python-audio-separator)）。
- GPU：`pip install "audio-separator[gpu]"`（onnxruntime-gpu / torch CUDA），Windows + NVIDIA 有 CI 覆盖（DirectML 路径）。
- 这是"想用 UVR 模型但要 headless"的正解。

### 2.4 spleeter（Deezer）——不推荐

- https://github.com/deezer/spleeter ，MIT，CLI 友好、快（T4 上 3 分钟歌约 3 秒），但 **2019 年发布、2020 年后无实质更新**，分离质量明显落后（vocals SDR 6.9 dB vs demucs 9.2 dB，[对比](https://stemsplit.github.io/demucs-onnx/comparison/)）。新项目没有理由选它。

### 2.5 其他 2024–2026 活跃方案（了解即可）

- **MVSEP-MDX23 / BS-RoFormer / MelBand-RoFormer / SCNet**：当前 MVSEP 榜单 SOTA 梯队（[mvsep.com](https://mvsep.com/)，[ZFTurbo/MVSEP-MDX23](https://github.com/ZFTurbo/MVSEP-MDX23-music-separation-model)，MDX23C 获 MVSEP 挑战赛 Leaderboard C 第三名）。原始 repo 集成复杂、权重许可不一；实用路径是经 audio-separator 加载 RoFormer 系 ckpt。对"剥 BGM"这个任务属于杀鸡用牛刀。
- **demucs 移植版**：ONNX 导出（[stemsplit.io](https://stemsplit.io/blog/htdemucs-ft-onnx-export)）、MLX 版（[demucs-mlx](https://github.com/ssmall256/demucs-mlx)，Apple Silicon 73x 实时）——证明 demucs 推理很轻，但 Windows + CUDA 直接用官方 PyTorch 版即可。
- **SAM-Audio（Meta）**：新 denoising 模型，但 2026 年论文实测其在 zero-shot ASR 预处理上**反而经常降低** whisper 识别率（[arXiv 2603.04710](https://arxiv.org/html/2603.04710v1)）。暂不采用。

### 方案对比表

| 方案 | Windows 可装 | 8GB VRAM | 速度（GPU） | CLI | 许可证 | 结论 |
|---|---|---|---|---|---|---|
| demucs (htdemucs/_ft) | 官方支持 | 充裕（>2GB 即可） | 远快于实时（3min 歌 ~5–15s 级） | 官方 | 代码 MIT；权重有研究用途历史争议 | **主选** |
| audio-separator | pip，GPU extra | 充裕 | 取决于模型，ONNX 系很快 | 官方 CLI + API | MIT | **备选**（UVR 模型入口） |
| UVR GUI | 装得起但 GUI-only | — | — | **无官方 CLI** | MIT | 不集成，仅借模型 |
| spleeter | 可装（TF 老依赖） | 充裕 | 最快 | 官方 | MIT | 不推荐（停更+质量差） |
| RoFormer/MDX23C 系 | 经 audio-separator | 充裕 | 较慢 | 经 audio-separator | 模型各自不一 | 质量上限备选 |

## 3. 关键效果问题

### (a) vocals 轨对 BGM 歌声的抑制程度 —— 这是本研究最重要的否定性结论

- demucs 的 vocals 轨训练目标来自 MUSDB18 的 vocals stem 定义，而 MUSDB 的 vocals stem **包含全部歌声（主唱 + 伴唱/合唱）**（[MUSDB18 数据集](https://sigsep.github.io/datasets/musdb.html)；demucs 训练数据说明见 [README](https://github.com/facebookresearch/demucs)）。
- 因此 **BGM 里的歌声本质上是"另一个 vocals"，会和对白一起留在 vocals 轨**。乐器（鼓/贝斯/其他）能被干净剥掉，歌声不能。社区在 UVR 里解决"主唱 vs 伴唱"用的是专门的 Karaoke 模型（见 §2.2），但注意维度错位：**Karaoke 模型区分的是主唱/伴唱，不是说话/唱歌**——BGM 若是一首有主唱的完整歌曲，其主唱正是 karaoke 模型要保留的 lead vocal，帮不上忙。
- 结论：**对"带歌词 BGM"场景，任何音乐源分离模型都无法把 BGM 歌声从对话中剥掉。** 可行的只有时序区分（何时在说话、何时只有音乐）或 ASR 侧抑制。

### (b) 分离后人声轨的音质损失对 whisper 准确率的影响 —— 有公开实测，结论"短句有益、长音频直接替换有害"

- 一手证据 [arXiv 2506.15514 "Exploiting Music Source Separation for Automatic Lyrics Transcription with Whisper"](https://arxiv.org/abs/2506.15514)（2025，用 demucs + Whisper 做歌词转写）：
  - 短句（short-form）：在分离出的 vocals 上转写，相比原始混音 WER 改善。
  - 长音频（long-form）：**直接把分离 vocals 整段喂给 Whisper 会导致转写质量显著退化**（论文引用并复现了该现象），原因是分离引入的 artifacts 与长音频切分边界错位。作者提出的正解是**用分离结果当 vocal activity detector 推导切分边界**，转写仍在原音频片段上做——该方案稳定优于 Whisper 原生长音频算法。配套代码：[jaza-syed/mss-alt](https://github.com/jaza-syed/mss-alt)。
- 旁证：[arXiv 2603.04710](https://arxiv.org/html/2603.04710v1)（SAM-Audio + Whisper）：提升感知音质的 denoise 预处理在 zero-shot ASR 上经常**降低**识别率——"听着更干净"≠"whisper 认得更准"。
- 工程向实测（二手，供参考）：日语技术博客用 jiwer 实测"分离 → 16kHz → VAD → Whisper"流水线，结论同样是"BGM 场景有效但会翻车，需要分场景启用"（[tomodahinata.com](https://tomodahinata.com/en/blog/source-separation-asr-preprocessing-whisper-accuracy)）。
- 另有已知 artifact：分离后的 vocals 是"湿人声"（混响残留），必要时可用 UVR De-Echo/De-Reverb 模型二次处理（[UVR issue #469](https://github.com/Anjok07/ultimatevocalremovergui/issues/469)）；但对 whisper 转写而言混响通常不是主要误差源。

### (c) 更有针对性的路线

1. **speech/music 区段检测：inaSpeechSegmenter**（[github.com/ina-foss/inaSpeechSegmenter](https://github.com/ina-foss/inaSpeechSegmenter)，MIT，pip 安装，CNN 把音频切成 speech(男/女)/music/noise 区段）。用在转写前：music-only 区段直接跳过（根除歌词字幕的来源），speech 区段正常转写，重叠区段走分离。这是针对"歌词混入字幕"最对症的工具。
2. **分离轨当 VAD 用**（2506.15514 的长音频算法）：vocals 轨能量包络 → 切分边界 → 原音频切片段落转写。比 silero-VAD 更能扛 BGM（VAD 在音乐段常误判为语音）。
3. **whisper 层面抑制**（已在流水线内，列出可加强项）：
   - VAD filter（whisper-ctranslate2 `--vad_filter`，已开）；
   - `condition_on_previous_text=False`（切断幻觉在 chunk 间的传播，[whisper Discussion #679](https://github.com/openai/whisper/discussions/679)）；
   - `no_speech_threshold` / `logprob_threshold` / `compression_ratio_threshold`（幻觉三件套，已开）；
   - **坑**：whisper-ctranslate2 的 `--batch_size` 批处理模式会**静默忽略**上述全部幻觉参数（[whisper-ctranslate2 README](https://github.com/Softcatala/whisper-ctranslate2)）。若未来想开批处理加速，注意权衡。
4. **WhisperX**（[m-bain/whisperX](https://github.com/m-bain/whisperX)）：VAD 切分 + 默认 `condition_on_prev_text=False`，论文报告降低 WER。如需重构转写层可评估，但与现有 whisper-ctranslate2 流水线替换成本较高。

## 4. 推荐落地

### 主选：分情况流水线（全部现成工具拼装）

```bash
# 一次性安装（venv 内）
pip install demucs inaSpeechSegmenter
# demucs GPU：按官方 Windows 文档装 CUDA 版 PyTorch
# https://github.com/facebookresearch/demucs/blob/main/docs/windows.md

# 1) 抽取音频
ffmpeg -i input.mp4 -vn -ac 1 -ar 44100 audio.wav

# 2) speech/music 分段（判断 BGM 是否含歌声 / 哪些段是纯音乐）
ina_speech_segmenter -i audio.wav -o segments_csv/

# 3) 对"音乐与人声重叠"或"BGM 为纯音乐"的视频做人声分离
demucs --two-stems=vocals -n htdemucs_ft --out out/separated audio.wav
#   更快：-n htdemucs；显存紧张（8GB 一般不需要）：--segment 6

# 4) 转写策略
#    - 纯 music 区段：跳过，不喂 whisper
#    - speech 区段：whisper 转写原音频（保持现有幻觉三件套 + condition_on_previous_text=False）
#    - BGM 无歌声的重叠区段：转写 demucs vocals 轨
#    - BGM 含歌声的重叠区段：分离帮不上忙；用 vocals 轨 + 严格 VAD/no_speech 阈值减少歌词幻觉，
#      残余歌词靠 LLM 审计环节兜底（现有 auditor 可针对"歌词特征"加规则）
```

### 备选：audio-separator（需要 UVR 系模型时）

```bash
pip install "audio-separator[gpu]"
# 例：karaoke 二级分离（主唱 vs 伴唱）、去混响等
audio-separator audio.wav --model_filename "UVR_MDXNET_KARA_2.onnx"
audio-separator --list_models   # 查看全部可用模型（含 MDX23C、RoFormer 系）
```

### 已知坑清单

1. **分离分不掉 BGM 歌声**（§3a）——不要指望 demucs vocals 轨能去歌词；这是模型定义层面的限制。
2. **长音频直接喂分离 vocals 会退化**（§3b，2506.15514）——分离轨用于检测/局部片段，别整段替换。
3. whisper-ctranslate2 `--batch_size` 会禁用幻觉相关参数（[README](https://github.com/Softcatala/whisper-ctranslate2)）。
4. htdemucs_ft 是 4 模型集成，约 4 倍耗时；长视频用 htdemucs 或调 `--segment`。
5. Windows 上 demucs GPU 需先装 CUDA 版 PyTorch（先 `pip uninstall torch torchaudio` 再装 cuXXX 版，[windows.md](https://github.com/facebookresearch/demucs/blob/main/docs/windows.md)）。
6. UVR GUI 无官方 CLI（同妙幕教训）；uvr-headless 类 fork 维护性存疑，用 audio-separator 替代。
7. demucs 权重许可历史上有"研究用途"争议（[HF 讨论](https://huggingface.co/adefossez/HTDemucs/discussions/1)）；本地个人使用无碍，勿把权重再分发进产品。
8. 分离后人声有混响/artifacts（湿人声）；转写层面通常可忽略，追求干净可加 De-Reverb 模型（audio-separator 提供）。

## 5. 来源汇总

一手来源：

- demucs 仓库 / Windows 文档 / 许可证：https://github.com/facebookresearch/demucs 、 https://github.com/facebookresearch/demucs/blob/main/docs/windows.md 、 https://github.com/facebookresearch/demucs/blob/main/LICENSE
- demucs 速度/显存 issue：https://github.com/facebookresearch/demucs/issues/426 ；two-stems 行为：https://github.com/facebookresearch/demucs/issues/511
- arXiv 2506.15514（MSS + Whisper 歌词转写）：https://arxiv.org/abs/2506.15514 ；代码 https://github.com/jaza-syed/mss-alt
- arXiv 2603.04710（denoise 反而降低 zero-shot ASR）：https://arxiv.org/html/2603.04710v1
- MUSDB18 数据集定义：https://sigsep.github.io/datasets/musdb.html
- UVR 仓库（MIT、GUI-only）及 Karaoke/De-Reverb 讨论：https://github.com/Anjok07/ultimatevocalremovergui 、 discussions [#1096](https://github.com/Anjok07/ultimatevocalremovergui/discussions/1096) / [#1250](https://github.com/Anjok07/ultimatevocalremovergui/discussions/1250) 、 issue [#469](https://github.com/Anjok07/ultimatevocalremovergui/issues/469)
- audio-separator：https://github.com/nomadkaraoke/python-audio-separator 、 https://pypi.org/project/audio-separator/ 、 LICENSE: https://github.com/nomadkaraoke/python-audio-separator/blob/main/LICENSE
- inaSpeechSegmenter：https://github.com/ina-foss/inaSpeechSegmenter 、 https://pypi.org/project/inaSpeechSegmenter/
- whisper-ctranslate2（batch 模式忽略幻觉参数）：https://github.com/Softcatala/whisper-ctranslate2
- whisper 幻觉讨论：https://github.com/openai/whisper/discussions/679 、 https://github.com/openai/whisper/discussions/1873
- WhisperX：https://github.com/m-bain/whisperX
- MVSEP / MDX23C / RoFormer：https://mvsep.com/ 、 https://github.com/ZFTurbo/MVSEP-MDX23-music-separation-model

二手/工程向参考（非关键论断依据）：

- https://stemsplit.github.io/demucs-onnx/comparison/ （SDR 对比、T4 延迟）
- https://github.com/nethum529/Filmroom/issues/9 （BGM+人声 → whisper 失败模式描述）
- https://tomodahinata.com/en/blog/source-separation-asr-preprocessing-whisper-accuracy （工程实测）
