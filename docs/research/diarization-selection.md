# 研究：说话人分离（diarization）本地选型与词级时间戳对齐

> 对应 issue：#8（阻塞 #15、#12）｜调研日期：2026-08-30
> 目标环境：Windows 10/11 + RTX 3070 8GB VRAM + Python 3.10 venv；现有转写为 whisper-ctranslate2（faster-whisper/CTranslate2，large-v3），产出词级时间戳 JSON。
> 原则：只拼现成开源工具（pip 可装），不自研软件；本仓库本身不涉及商业使用，但许可证仍需记录。

## 结论 / 推荐

**主选：`pyannote.audio` 3.3.x + `pyannote/speaker-diarization-3.1`**。

理由：在 Windows 上安装路径最短（`torch>=2.0.0`，无 torchcodec/FFmpeg-DLL 依赖）；模型 MIT 协议；显存正常占用 <1GB；原生支持重叠语音输出；中文会议基准（AISHELL-4 DER 12.2）可用。与现有 venv 共存风险最低。

**备选 1（精度优先）：`pyannote.audio` 4.x + `pyannote/speaker-diarization-community-1`**。中文基准更好（AISHELL-4 11.7、AliMeeting 20.3 vs 3.1 的 24.5），「独占式（exclusive）」输出让词归属更简单；但强制 `torch==2.8.0`（4.0.2 起 pin 死）+ torchcodec（Windows 需 FFmpeg shared DLL，已知坑），且 embedding 阶段存在 9–12GB 显存尖峰的已知 bug（#1963），8GB 卡需降 batch 或分段规避。

**备选 2（零门槛兜底）：sherpa-onnx 离线说话人分离**。pyannote 分割模型的 ONNX 版 + 3D-Speaker CAM++/NeMo embedding，纯 CPU、官方支持 Windows、模型 Apache-2.0 无 HF 门禁。适合不想注册 HF 或 GPU 环境出问题时兜底；缺点是长音频慢（社区反馈 21 分钟音频约 5 分钟）。

**不选**：whisperX 整套（其 diarization 就是 pyannote，且会替换我们已验证的转写栈、锁死 torch 版本；但其 `assign_word_speakers` 对齐算法值得直接照抄）；NeMo（官方不支持原生 Windows，仅 WSL2）；SpeechBrain / 3D-Speaker 原生（无开箱即用的成品 pipeline，组装成本高）；pyannoteAI 云端 Precision-2（付费 API，违背「本地」前提，仅作精度上限参考）。

**对齐策略**：词级归属照抄 whisperX 的算法——每词与 diarization 段求时间交集，取**交集时长最大**的说话人（最大重叠多数表决）；无交集时回退到**时间最近段**；字幕行级取行内主导说话人。详见 §3。

---

## 1. 候选方案盘点

### 1.1 pyannote.audio（主推家族）

开源工具包 MIT 协议，预训练 pipeline 托管在 HuggingFace（**gated = auto**：需注册 HF 账号、在模型页点同意条款、创建 read token；同意后可离线使用本地缓存/本地 config）。

| 组合 | 3.3.x + `speaker-diarization-3.1` | 4.x + `speaker-diarization-community-1` |
|---|---|---|
| 工具包协议 | MIT | MIT |
| 模型协议 | MIT（gated，还需另接受 `segmentation-3.0` 条款） | CC-BY-4.0（gated，只需接受这一个） |
| torch 要求 | `torch>=2.0.0`、`torchaudio>=2.2.0`、speechbrain>=1.0（无 torchcodec） | `torch>=2.8.0`、`torchaudio>=2.8.0`、`torchcodec>=0.7.0`（4.0.2 版曾 pin 死 `==2.8.0`） |
| 重叠语音 | **原生支持**（多标签 segmentation，可输出重叠段） | 默认「exclusive」独占式输出（每时刻只归一人），利于和转写对齐 |
| 中文基准 DER | AISHELL-4 12.2 / AliMeeting 24.5 / RAMC 22.2 / MSDWild 25.4 | AISHELL-4 11.7 / AliMeeting 20.3 / RAMC 20.8 / MSDWild 22.8 |
| 显存 | 正常各阶段 <1GB | 正常 <1GB，但 embedding 阶段有 9–12GB 尖峰 bug（见 §4 坑） |
| 速度参考 | — | 社区版 H100 上 31–37s / 小时音频（README benchmark） |

来源：
- 3.3.2 依赖清单：https://github.com/pyannote/pyannote-audio/blob/3.3.2/requirements.txt
- 4.x 依赖清单（torch>=2.8 / torchcodec>=0.7）：https://github.com/pyannote/pyannote-audio/blob/main/pyproject.toml
- 4.0.2 pin torch 的 changelog 与原因（torchcodec segfault）：https://github.com/pyannote/pyannote-audio/blob/main/CHANGELOG.md
- Benchmark 表（2025-09 更新，含 AISHELL-4/AliMeeting/RAMC/MSDWild 等中文集）：https://github.com/pyannote/pyannote-audio/blob/main/README.md
- 3.1 模型卡（gated、MIT、需接受 segmentation-3.0 + speaker-diarization-3.1 两处条款）：https://huggingface.co/pyannote/speaker-diarization-3.1
- community-1 模型卡（exclusive diarization 设计目标即「与转写时间戳更容易对齐」）：https://huggingface.co/pyannote-community/speaker-diarization-community-1
- 门禁与协议实测（HF API）：`https://huggingface.co/api/models/pyannote/speaker-diarization-3.1` → `gated:auto, license:mit`；`.../speaker-diarization-community-1` → `gated:auto, license:cc-by-4.0`
- 离线使用（本地模型 + 本地 config）：https://github.com/pyannote/pyannote-audio/blob/main/tutorials/community/offline_usage_speaker_diarization.ipynb

**pyannoteAI 商业线（仅参考）**：Precision-2 为付费/自托管商业管线，官方称平均比 community-1 准 28%，不开源。来源：https://docs.pyannote.ai/models

**Windows 可装性**：3.3.x 是纯 torch 依赖，`pip install pyannote.audio==3.3.2` + `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121`（或更高 CUDA）即可，与 RTX 3070 无兼容问题。4.x 需额外解决 torchcodec 的 FFmpeg shared 库（见 §4）。

### 1.2 whisperX

- 本质：**faster-whisper（CTranslate2）批推理 + Silero VAD 切段 + wav2vec2 forced alignment（音素分类 + DTW）+ pyannote diarization**。它的说话人分离就是调 pyannote（最新版默认 `pyannote/speaker-diarization-community-1`），同样需要 HF token。
- 依赖（3.8.x）：`torch~=2.8.0`、`pyannote-audio>=4.0.0`、torchcodec（win32 也标记安装）。协议 BSD-2-Clause。
- 对我们的价值：diarization 部分没有增量；**其词→说话人归属算法（`whisperx/diarize.py` 的 `assign_word_speakers`）是我们的对齐实现范本**（§3）。
- 结论：不整套引入（会替换已验证的转写命令、并继承 4.x 的全部版本坑），只借鉴对齐代码逻辑。

来源：https://github.com/m-bain/whisperX 、https://github.com/m-bain/whisperX/blob/main/pyproject.toml 、https://github.com/m-bain/whisperX/blob/main/whisperx/diarize.py ；对齐原理论文（INTERSPEECH 2023）：https://arxiv.org/abs/2303.00747

### 1.3 NVIDIA NeMo（Sortformer / MSDD）

- Sortformer 是端到端 Transformer diarizer（arXiv 2409.06656），有离线/流式版本，**上限 4 个说话人**（`diar_sortformer_4spk`）。
- 安装面：官方支持矩阵只列 Linux（x86_64/aarch64）+ WSL2，**原生 Windows 不在支持矩阵**；安装文档以 `apt-get install libsndfile1` 等 Linux 步骤为前提。
- 8GB 显存够用（模型不大），但系统门槛直接出局。

来源：https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/asr/speaker_diarization/intro.html 、https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2.1 、https://docs.nvidia.com/nemo-platform/v0.3.0/documentation/reference/support-matrix 、https://arxiv.org/abs/2409.06656

### 1.4 SpeechBrain

- 提供 AMI 会议集的 diarization recipe（ECAPA-TDNN 嵌入 + 谱聚类），是「菜谱/研究代码」而非开箱 pipeline；模型以英文 VoxCeleb 系为主，中文会议表现无官方数据。
- Windows 可装（纯 torch），但组装、调参成本高，不符合「拼现成工具」。

来源：https://github.com/speechbrain/speechbrain/tree/develop/recipes/AMI/Diarization 、https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb

### 1.5 3D-Speaker（阿里）

- Apache-2.0，CAM++ 说话人嵌入在中文（3D-Speaker 语料，14 种普通话方言、10000+ 说话人）上训练，中文表现有据可查；但官方 diarization 走 modelscope + shell 脚本（`egs/3dspeaker/speaker-diarization/run_audio.sh`），Windows 原生跑通成本高。
- **曲线路径**：其 CAM++ 模型已被 sherpa-onnx 导出为 ONNX（见 1.6）。

来源：https://github.com/modelscope/3D-Speaker 、https://arxiv.org/abs/2403.19971 、https://modelscope.cn/models/damo/speech_campplus_sv_zh-cn_3dspeaker_16k

### 1.6 sherpa-onnx（备选 2）

- k2-fsa 的离线推理框架，**官方支持 Windows**（有预编译包），提供 Python/C#/C 等 API。
- 说话人分离 = pyannote segmentation 的 ONNX 版 + embedding（3D-Speaker CAM++ / NeMo / WeSpeaker 可选）+ 聚类，**模型 Apache-2.0、无 HF 门禁**，纯 CPU 可跑。
- 已知缺点：长音频 CPU 速度慢（社区反馈 21 分钟 WAV 约 5 分钟）；精度与 pyannote 原生有差距。

来源：https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html 、https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/models.html 、https://github.com/k2-fsa/sherpa-onnx/discussions/3233

## 2. 环境适配小结（Windows + RTX 3070 8GB + py3.10）

- pyannote 4.x `requires-python = ">=3.10"`，3.3.x `python_requires = >=3.9`，均兼容现有 venv。
- 现有 venv 是 CTranslate2 系（无 torch）。装 pyannote 会引入 torch（约 2.5GB  wheel + CUDA DLL），磁盘与依赖体积需预期。
- GPU 使用建议**串行**：先转写（faster-whisper large-v3 float16，峰值 5–6GB）再 diarization，不要并行，避免 8GB 撞顶。
- pyannote 有可选匿名遥测（opt-in），不在意可忽略。

## 3. 与现有流水线的对齐策略

### 3.1 输入与输出

- 转写侧（已有）：whisper-ctranslate2 `--word_timestamps True --pretty_json True` 产出 JSON：`segments[].words[] = {word, start, end, probability}`。
- diarization 侧：pyannote 输出 `(start, end, speaker)` 段序列（3.1 可含重叠段；community-1 为独占式）。

### 3.2 词 → 说话人归属算法（照抄 whisperX `assign_word_speakers`）

源码：https://github.com/m-bain/whisperX/blob/main/whisperx/diarize.py

1. 把 diarization 段按 start 排序建区间树（whisperX 用排序数组 + 二分，O(log n) 查询）。
2. **词级**：对每词 `[w_start, w_end]` 查询所有重叠段，按说话人累计**交集时长**，取最大者 → 即「最大重叠多数表决」。词跨说话人边界时自然归到占比更大的一侧。
3. **无重叠兜底**（`fill_nearest`）：词落在 diarization 空白（如 VAD 漏检的间隙）时，取词中点最近段的说话人；也可选择继承前一词的说话人。
4. **行/句级**：对整个字幕行 `[start, end]` 同样取交集时长最大的说话人，用于 SRT 标注（如行首加说话人标签）。

对 community-1 独占式输出，上述算法退化为简单区间查询，边界词误差集中在说话人切换点附近（±一个词）。对 3.1 的重叠输出，算法会把重叠区的词全部归给重叠时长更大的一方——**重叠区的第二说话人词语会丢失归属**，这是已知边界（§3.4）。

### 3.3 whisperX 自带对齐的原理（供理解，不引入）

whisperX 解决的是 whisper 原生时间戳漂移问题：Silero VAD 切出语音段 → 批推理转写 → 用语种对应的 wav2vec2 模型对音频做音素分类 → 与转写文本做 DTW 对齐，得到词边界。我们已由 whisper-ctranslate2 产出词级时间戳且第 2 步（resegment）以词级精度工作，**不需要它的 ASR/alignment 层**，只需要 diarization + 词归属。来源：https://arxiv.org/abs/2303.00747

### 3.4 重叠语音（多人同时说话）能力边界

- pyannote 3.1：多标签 segmentation **能检测并输出重叠段**（同一时刻两个 speaker 段并存）；但词归属阶段（无论 whisperX 还是我们的照抄版）每词只能取一个说话人，重叠信息在归属时被压扁。
- community-1：设计上就是独占式输出，不表示重叠；重叠语音的误差被计入 DER。官方 benchmark 全部为「无 collar、含重叠」的严格口径：CALLHOME community-1 26.7%、AMI-SDM 19.9%——**重叠语音仍是所有方案的主要误差源**。
- sherpa-onnx：分割模型同源自 pyannote，行为类似；embedding+聚类对重叠段倾向归一。
- 对本项目（单人讲解/双人对话类视频为主）：重叠占比低，主选方案足够；若未来处理多人圆桌会议，重叠区字幕需人工兜底。

来源：https://huggingface.co/pyannote/speaker-diarization-3.1（overlapped-speech-detection 标签与评测口径）、README benchmark 表、https://github.com/pyannote/pyannote-audio/blob/6328b97b/tutorials/overlapped_speech_detection.ipynb

## 4. 安装与运行要点 / 已知的坑

### 主选（3.3.x + 3.1）

```sh
venv/Scripts/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
venv/Scripts/pip install "pyannote.audio==3.3.2"
# 浏览器登录 HF，接受两个 gated 模型条款：
#   https://huggingface.co/pyannote/segmentation-3.0
#   https://huggingface.co/pyannote/speaker-diarization-3.1
# 创建 read token: https://huggingface.co/settings/tokens
```

```python
from pyannote.audio import Pipeline
import torch
pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=HF_TOKEN)
pipeline.to(torch.device("cuda"))
out = pipeline({"waveform": wav, "sample_rate": 16000}, num_speakers=None)  # 16kHz 单声道
diar = out.speaker_diarization  # 可 itertracks(yield_label=True)
```

- 音频输入用 ffmpeg 先转 16k 单声道 wav（仓库已有 ffmpeg 约定），绕开任何解码依赖。
- 已知 gated 403 问题：接受条款后仍 403 时，确认 token 为 read 权限且账号已验证邮箱（HF 论坛已知案例）。

### 备选 1（4.x + community-1）的坑

- **torchcodec/FFmpeg**：torchcodec 音频解码需要 FFmpeg 的 **shared** 版 DLL；Windows 上 `Could not load libtorchcodec` 为高发问题（pyannote issue #1940），需 conda 版 ffmpeg 或手动 `os.add_dll_directory`（Python ≥3.8 必须显式加 DLL 目录；conda ffmpeg 还依赖 `Library\mingw-w64\bin`）。torchcodec README 明确 Windows 装的是 CPU wheel，CUDA wheel 需另指 `--index-url`。
  - https://github.com/pyannote/pyannote-audio/issues/1940 、https://github.com/pytorch/torchcodec
- **版本锁死**：4.0.2 起曾 pin 死 `torch==2.8.0`（为规避 torchcodec segfault），与依赖 torch 2.9+ 的库冲突；whisperX 亦 pin `torch~=2.8.0`。来源：https://github.com/pyannote/pyannote-audio/issues/1976 、https://github.com/pyannote/pyannote-audio/issues/1974
- **显存尖峰（8GB 卡的关键风险）**：issue #1963 实测 embedding 阶段某个 batch（形状 `(29, 1, 160000)`）因 cuDNN 算法选择导致 allocated 冲到 10.5GB / reserved 12GB。缓解：调小 embedding `batch_size`、把长音频按静音分段后分别 diarize、或该步回退 CPU。
  - https://github.com/pyannote/pyannote-audio/issues/1963

### 通用坑

- **HF token 是三选一流程的共同门槛**（3.1 要接受 2 个模型条款，community-1 要 1 个）；接受条款是一次性动作，之后可离线（本地缓存/本地 config）。
- diarization 与转写**串行**跑，跑完转写释放 GPU 再跑 diarization（torch 的 CUDA caching allocator 不主动还显存，同进程内注意 `torch.cuda.empty_cache()`）。
- 说话人数量已知时传 `num_speakers=N`（或 `min/max_speakers`），能显著降低计数错误（community-1 的主要改进点即计数/归属）。
- 输出标签是 `SPEAKER_00/01...` 聚类标签，**不保证跨文件一致**；跨视频需要说话人指纹（voiceprint）则要另行处理（pyannoteAI Precision-2 的卖点之一）。

## 5. 后续落地建议（超出本研究范围，供 #15/#12 参考）

1. 主工作流新增「diarization」环节：ffmpeg 抽 16k 单声道 wav → pyannote → `out/<视频名>/diarization.json`（段列表）。
2. 新增「词归属」环节：按 §3.2 算法把 `source.json` 的词打上 speaker 标签，供 resegment subagent 在断句时优先在说话人切换处断行，并在 SRT 中标注说话人。
3. 若 4.x 在目标机踩到 torchcodec 坑，回退主选（3.3.x）即可，两者 JSON 输出结构一致，对齐代码不变。

## 附：一手来源清单

- pyannote-audio 仓库 / README / CHANGELOG / 依赖：https://github.com/pyannote/pyannote-audio
- pyannote 模型卡与门禁：HF `pyannote/speaker-diarization-3.1`、`pyannote/segmentation-3.0`、`pyannote/speaker-diarization-community-1`（及 `/api/models/...` 元数据）
- pyannote 已知问题：issues #1940（torchcodec DLL）、#1963（显存尖峰）、#1974/#1976（torch 版本锁）
- whisperX 仓库与对齐源码：https://github.com/m-bain/whisperX ；论文 https://arxiv.org/abs/2303.00747
- NeMo diarization 文档 / Sortformer：https://docs.nvidia.com/nemo-framework/user-guide/latest/nemotoolkit/asr/speaker_diarization/intro.html 、https://arxiv.org/abs/2409.06656
- SpeechBrain AMI recipe：https://github.com/speechbrain/speechbrain/tree/develop/recipes/AMI/Diarization
- 3D-Speaker：https://github.com/modelscope/3D-Speaker 、https://arxiv.org/abs/2403.19971
- sherpa-onnx diarization：https://k2-fsa.github.io/sherpa/onnx/speaker-diarization/index.html
- pyannoteAI 商业模型对比：https://docs.pyannote.ai/models
- torchcodec 平台支持说明：https://github.com/pytorch/torchcodec
