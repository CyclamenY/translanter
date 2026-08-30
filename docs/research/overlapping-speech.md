# 重叠语音处理调研：只保留真人解说、剔除游戏内角色语音

> 对应 issue：#10「重叠语音：真人解说与游戏角色语音同时说话时的字幕过滤机制」
> 调研日期：2026-08-30
> 问题：游戏录播中真人实况解说（可能多人）与游戏内角色语音时间重叠，字幕只保留真人说话。盘点四类本地机制并给出推荐。
> 环境基线：Windows 10/11，RTX 3070 8GB，Python 3.10 venv，已有 whisper-ctranslate2（large-v3）转写环节。

## 结论与推荐

**主选路线：(d) 声纹聚类 + 人工挑选，落地形态 =「先转写 + diarization，再按说话人类别过滤时间轴/文本」**，与 (a) 是同一工具链的两种用法：

1. 用 **WhisperX**（`pip install whisperx`）或「whisper-ctranslate2 转写 + pyannote `speaker-diarization-community-1` 并行跑，再按时间轴对齐」得到带说话人标签的词级/段级字幕。重叠段在 pyannote 的非 exclusive 输出中**同时带两个说话人标签**，因此过滤掉「角色」类标签后，重叠段的真人语音时间轴**保留得住**。
2. 对每个说话人类别抽几段样本人工试听，圈定要保留的「真人」类别（支持多个真人）。
3. 按类别过滤 SRT。此路线全部为 pip 可装的成熟工具，无需拼研究代码。

**备选/增强**：重叠严重导致角色语音漏进转写文本时（whisper 会把重叠段两人说的话混在一起转写），对检出的重叠段（pyannote `overlapped-speech-detection` pipeline 可直接给出重叠区间）单独走 **(c) 目标说话人提取**（给真人录一段参考音频做 enrollment，用 WeSep/SpEx+ 类模型从混合音中抽出真人语音再单独转写）。

**不推荐主用**：(b) 盲语音分离（SepFormer/Conv-TasNet/SuDoRM-RF）——现成预训练模型几乎全部固定输出 2 路、在干净朗读语料（WSJ0-2Mix/LibriMix）上训练，说话人数量未知时行为不可控，对带 BGM/音效的游戏音频泛化差。

**先决检查（成本最低的最优解）**：若素材是自己用 OBS 录的，确认是否开启了多音轨录制——OBS 支持最多 6 条独立音轨，麦克风与游戏音频可分轨录制；若麦克风在独立音轨上，「剔除角色语音」问题直接消失，只需取麦克风轨转写。
来源：https://obsproject.com/eu/wiki/advanced-recording-guide-with-multi-track-audio

---

## 1. 候选机制盘点

### (a) diarization + 说话人过滤（pyannote）

**对重叠语音的处理行为**：

- pyannote 的分割模型用 **powerset 多标签编码**：`pyannote/segmentation-3.0` 输出 7 类 = 非语音、说话人#1/#2/#3、以及「#1且#2」「#1且#3」「#2且#3」三种重叠组合。即**重叠段会被显式标成「两个说话人同时说话」**，而不是被强行归给某一个人。
  来源：https://huggingface.co/pyannote/segmentation-3.0
- diarization pipeline 的返回值同时包含两份结果：`speaker_diarization`（含重叠，同一时间段可有两个标签）和 `exclusive_speaker_diarization`（每个时刻只保留一个最可能被转写的说话人，专为对齐 ASR 设计）。这是源码中 `DiarizeOutput` dataclass 的字段定义。
  来源：https://github.com/pyannote/pyannote-audio/blob/6328b97b/src/pyannote/audio/pipelines/speaker_diarization.py ；https://huggingface.co/pyannote/speaker-diarization-community-1
- 另有独立的**重叠语音检测 pipeline**：`pyannote/overlapped-speech-detection`，直接输出重叠区间（Annotation），可用来定位需要特殊处理的段落。
  来源：https://huggingface.co/pyannote/overlapped-speech-detection

**过滤「角色」标签后重叠段真人语音是否保留**：保留得住。用**非 exclusive** 输出时，重叠段同时带真人和角色两个标签，按「角色」标签做减法后真人标签的时间轴仍在；只是该段的转写文本质量取决于 whisper 在重叠语音上的表现（见「已知坑」）。若用 exclusive 输出则相反——重叠段被二选一，角色若「赢」了该段，真人语音就丢了，因此**本场景必须用非 exclusive 输出**。
来源：https://github.com/pyannote/pyannote-audio/discussions/1157（官方讨论串：处理重叠语音时 diarization 与 ASR 对齐的困难）

**适配度**：高。diarization 本身不区分「真人/角色」，它只聚类出不同声纹——游戏角色如果是固定几个配音演员，往往会各自成类，正好可被整类剔除；角色众多且每人只说几句时聚类会碎（见「已知坑」）。

**成熟度**：开箱即用。`pip install pyannote.audio`（PyTorch 生态，Windows 可装；模型托管在 HuggingFace，需注册账号、接受 `pyannote/speaker-diarization-community-1` 等 gated model 的使用条款并配 token；下载后可离线使用）。
来源：https://github.com/pyannote/pyannote-audio ；https://huggingface.co/pyannote/speaker-diarization-community-1 ；https://github.com/pyannote/pyannote-audio/blob/main/tutorials/community/offline_usage_speaker_diarization.ipynb

### (b) 盲语音分离（SepFormer / Conv-TasNet / SuDoRM-RF）

- **可行性**：这类模型把混合音分成**固定路数**的独立音轨。最成熟的现成模型是 SpeechBrain 的 `sepformer-wsj02mix`——WSJ0-2Mix 上 22.4 dB SI-SNR，但**只输出 2 路**，且训练数据是干净录音棚朗读语音的 2 人混合。
  来源：https://huggingface.co/speechbrain/sepformer-wsj02mix ；https://speechbrain.readthedocs.io/en/latest/API/speechbrain.inference.separation.html
- **说话人数量未知时的行为**：不可控。PIT（permutation invariant training）类模型输出通道数在训练时固定；输入说话人少于通道数会产生空/重复轨道，多于通道数则多人被压进一路。解决「未知人数」本身就是研究问题（如 Nachmani et al. 2020 专门发论文处理），没有成熟开源实现。
  来源：https://proceedings.mlr.press/v119/nachmani20a/nachmani20a.pdf ；https://github.com/kaituoxu/Conv-TasNet
- **Windows 本地可装性**：可以装（SpeechBrain / Asteroid 均为 pip 包，Asteroid 含 Conv-TasNet、DPRNN、SuDoRM-RF 实现与预训练模型），但没有面向「分离任意录播」的 CLI，需写少量脚本调 Python API。
  来源：https://github.com/asteroid-team/asteroid
- **适配度**：低。即使分离成功，得到的 N 路音轨仍需再做一遍「哪路是真人」的判别（等于把问题推给 diarization/声纹），且游戏 BGM/音效/角色配音与干净朗读语料差异大，分离质量预期明显劣化。作为纯音频预处理成本高、收益不确定。

### (c) 目标说话人提取（TSE，声纹 enrollment）

- **机制**：给目标说话人一段参考音频（几秒~几十秒），模型从混合音中只抽出该人的语音。对重叠语音是**样本级**的根治——抽出的音轨里角色语音被抑制，再送 whisper 转写就不会串词。
- **代表方案与成熟度**：
  - **WeSep**（wenet-e2e，Interspeech 2024）：专门的 TSE 工具包，支持 SpEx+、pBSRNN、pDPCCN、TF-GridNet 等模型，集成 Wespeaker 声纹。但 README 的 ToDo 清单中 **「Pretrained models」「CLI Usage」两项均未勾选**——即无官方预训练权重、无 CLI，属于要自己训或找第三方 checkpoint 的研究代码。有一个 HuggingFace demo space（2 人混合演示），说明存在演示 checkpoint。
    来源：https://github.com/wenet-e2e/wesep/blob/master/README.md ；https://www.isca-archive.org/interspeech_2024/wang24fa_interspeech.pdf ；https://huggingface.co/spaces/wenet-e2e/wesep-tse-2speaker-demo
  - **SpEx+**：官方代码开源（论文 arXiv:2005.04686），同样是研究代码，无 pip 包。
    来源：https://github.com/xuchenglin28/speaker_extraction_SpEx ；http://arxiv.org/pdf/2005.04686v1
  - **VoiceFilter / VoiceFilter-Lite**（Google）：论文与第三方实现（mindslab-ai/voicefilter）公开，Google 未开源权重；第三方仓库年久失修。
    来源：https://google.github.io/speaker-id/publications/VoiceFilter/ ；https://github.com/mindslab-ai/voicefilter
- **适配度**：中。对每个真人各录一段干净参考音频即可逐个提取，天然支持「多个真人」；对重叠段是治本方案。但全部需要拼研究代码/自训模型，工程量与维护成本高，不适合作为默认路线。
- **与 whisper 的组合**：必须先处理音频再转写（它产出的是音频而非标签）。

### (d) 声纹聚类 + 人工挑选

- **机制**：对全片做说话人 embedding 聚类 → 每类抽样本人工听 → 圈定保留类 → 按类过滤时间轴。
- **关键事实**：这**不需要单独的工具**——pyannote diarization 内部就是「分割 + embedding + 凝聚聚类」，`DiarizeOutput` 直接附带每个说话人类别的 embedding（`speaker_embeddings`，按 labels 顺序排列的 `(num_speakers, dimension)` 数组）。也就是说 (d) 与 (a) 是同一次 diarization 运行的两个视角：类已由聚类分好，人只需在每类里抽 1–2 段试听并贴「真人/角色」标签。
  来源：https://github.com/pyannote/pyannote-audio/blob/6328b97b/src/pyannote/audio/pipelines/speaker_diarization.py ；https://github.com/pyannote/pyannote-audio/blob/6328b97b/src/pyannote/audio/pipelines/clustering.py
- 若想脱离 pyannote 自建，可用 SpeechBrain 的 ECAPA-TDNN（`speechbrain/spkrec-ecapa-voxceleb`，pip 可装，专门支持提取 speaker embedding）自行做滑窗 embedding + 聚类，但这属于重复造轮子。
  来源：https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- **适配度**：最高。判别标准（「这是真人还是角色」）交给唯一可靠的裁判——人耳；聚类把人听的工作量从「听全片」压到「听几段样本」。多真人、多角色都自然支持。

## 2. 与 whisper 转写环节的组合方式

| 机制 | 组合方式 | 说明 |
|---|---|---|
| (a)/(d) | **先转写，再按时间轴过滤文本**（推荐） | whisper 对原始混合音转写；diarization 并行跑；按词/段时间戳对齐后剔除角色类的段。重叠段真人语音时间轴保留（非 exclusive 输出），文本可能含角色串词（见坑） |
| (b) 分离 | 先处理音频再转写 | 分离出的每路音轨分别转写，再决定保留哪路文本；链路长、环节多 |
| (c) TSE | 先处理音频再转写 | 对全片或仅重叠段提取真人音轨后单独转写，再与主时间轴合并 |

**现成组合工具：WhisperX**。`pip install whisperx`，Windows 有官方 CUDA 安装说明；faster-whisper 后端（与本仓库现有 whisper-ctranslate2 同宗），`--diarize` 直接调用 pyannote（当前用 community-1，需 HF token），wav2vec2 强制对齐出**词级时间戳**，输出每个词带说话人标签——正是「先转写再按说话人过滤」的一步到位实现。8GB 显存可跑 large 系列。
来源：https://github.com/m-bain/whisperX

注意：WhisperX 默认 diarization 会把重叠段归给单一说话人（其对齐逻辑按段取主说话人），若要利用「重叠段双标签」需绕过 WhisperX 的 assign-speakers 步骤，直接消费 pyannote 的非 exclusive Annotation 自行对齐。

## 3. 开箱即用程度对比

| 机制 | 代表工具 | pip 包 | 预训练模型 | CLI | 结论 |
|---|---|---|---|---|---|
| (a)/(d) | pyannote.audio / WhisperX | 有 | 有（HF gated，需 token） | WhisperX 有；pyannote 为 Python API | **开箱即用** |
| (b) 分离 | SpeechBrain SepFormer / Asteroid | 有 | 有（限 2 人干净语料） | 无 | 半开箱，效果存疑 |
| (c) TSE | WeSep / SpEx+ / VoiceFilter | 无（clone 源码） | 基本无 | 无 | 研究代码，需拼装 |

## 4. 已知坑

1. **whisper 在重叠语音上的串词**：whisper 是单流 ASR，重叠段会把两人的话混成一句或只挑响的一方转写。时间轴过滤能保住真人段的「框」，但框内文本可能含角色台词碎片；重叠占比高的素材需配合 (c) 或人工校对兜底。（pyannote 官方 ASR 对齐教程也指出 ASR 对重叠语音处理不好，故提供 exclusive 模式：https://docs.pyannote.ai/tutorials/diarization-asr-merge）
2. **角色聚类碎裂**：游戏角色多、每人台词少、语音带音效处理（电台音、怪物音）时，diarization 会把同一角色拆成多类或把角色并进真人类。缓解：人工挑选阶段允许把多个类都标为「剔除」；`min_speakers`/`max_speakers` 参数约束聚类数。
   来源：https://docs.pyannote.ai/tutorials/speaker-configuration
3. **声纹模型的训练域**：pyannote/ECAPA-TDNN 的 embedding 在真人电话/访谈语料（VoxCeleb 等）上训练，对配音演员的「角色音」（刻意变化的声线）区分度可能低于真人常态声线。
   来源：https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
4. **HF gated model 门槛**：pyannote 模型需在 HuggingFace 接受使用条款并配置 token（首次联网下载，之后可离线）。
   来源：https://huggingface.co/pyannote/speaker-diarization-community-1
5. **独占模式陷阱**：误用 exclusive diarization（或 WhisperX 默认对齐）会在重叠段丢掉真人语音，本场景务必用非 exclusive 输出。
   来源：https://github.com/pyannote/pyannote-audio/blob/6328b97b/src/pyannote/audio/pipelines/speaker_diarization.py
6. **分离模型的固定路数与域差**：(b) 路线在 >2 人重叠、带 BGM/音效的游戏音频上预期显著劣化，且无「哪路是真人」的判别能力。
   来源：https://huggingface.co/speechbrain/sepformer-wsj02mix ；https://proceedings.mlr.press/v119/nachmani20a/nachmani20a.pdf

## 附：若素材是自己录的——先查多音轨

OBS Studio 高级输出模式支持最多 6 条音轨，可把麦克风、游戏音频、系统声音分轨录制。若真人解说在独立音轨上，直接对该轨跑 whisper 即可，本调研的所有机制都不需要。仅当素材已混流（如下载的直播录像）时才走上面的路线。
来源：https://obsproject.com/eu/wiki/advanced-recording-guide-with-multi-track-audio
