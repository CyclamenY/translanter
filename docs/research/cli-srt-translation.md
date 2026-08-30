# CLI 模式 SRT 字幕翻译工具调研

> 对应 issue：#3 的补充调研（原调研 docs/research/srt-llm-translation.md 选定 GUI 方案妙幕 SmartSub；本调研回答"翻译步骤能否改为 CLI 模式"）
> 调研日期：2026-08-30（覆盖各工具截至 2025–2026 年的状态）
> 问题：有没有活跃的、CLI 可用的 SRT 字幕翻译工具，能接 DeepSeek / Kimi 等 OpenAI 兼容端点，并处理好长 SRT（千级条目、译文错位防护、断点续翻、术语一致性）？如果都不合格，才考虑推翻「不写新软件」的约束自写流程。

## 结论速览

**有合格的 CLI 工具，不需要自写。** 首选 **LLM-Subtrans**（machinewrapped/llm-subtrans）：真 CLI、原生 DeepSeek provider + 任意 OpenAI 兼容端点（Kimi 走 Custom Server）、scene/batch 两级分块、项目文件断点续翻、术语表、错位重试与后处理，是为"LLM 翻译字幕"这个场景专门设计的架构。强备选 **rockbenben/subtitle-translator** 的 `yarn cli`：原生 DeepSeek 与 Moonshot（Kimi）、时间码在本地剥离（模型物理上碰不到时间轴）、逐行缓存断点续翻，但 CLI 需克隆仓库 + yarn 安装，不是独立发行包。VideoCaptioner 的 CLI（`pip install videocaptioner`，安装最省事）也可用，但要注意其 `subtitle` 命令默认开启断句/优化（会改变条目数），纯翻译必须显式 `--no-split --no-optimize`。

**妙幕 SmartSub 确认无 CLI/headless 模式**：README 与文档站无任何命令行入口；GitHub issue #163「希望添加命令行功能」开放中，作者回复指向其早期 CLI 项目 VideoSubtitleGenerator——但该项目翻译只支持百度/火山/DeepLX/Ollama，不支持 OpenAI 兼容 LLM 端点，且已被作者定位为 SmartSub 的前身，不合格。

原调研的 GUI 结论不受影响：SmartSub 仍是 GUI 交互场景的首选；CLI 场景改用 LLM-Subtrans 即可，两者可以并存（甚至 SmartSub 继续承担校对环节）。

---

## 1. 硬性要求核查方法说明

每个候选按 7 条硬性要求打分：真 CLI / 自定义 OpenAI 兼容端点 / 长 SRT 处理 / 时间戳对齐保障 / 术语表与自定义提示词 / 维护状态 / 安装方式（Windows）。下文对每个候选区分「README 宣称」与「源码/文档证实」两级证据；维护状态用 GitHub API（pushed_at、最新 release 日期）与 PyPI 上传时间核实。

## 2. 严肃候选详评

### 2.1 LLM-Subtrans（machinewrapped/llm-subtrans）—— 首选

- **是什么**：开源（645 stars）专用字幕 LLM 翻译器，支持 `.srt` / `.ssa`/`.ass` / `.vtt`，Python 编写。CLI 与 GUI 双形态，GUI 只是 CLI 内核（PySubtrans）之上的壳。
  来源：https://github.com/machinewrapped/llm-subtrans ；https://github.com/machinewrapped/llm-subtrans/blob/main/docs/architecture.md
- **真 CLI（文档证实）**：`llm-subtrans` 控制台命令直接翻译文件，如 `llm-subtrans -s <server> -e <endpoint> -k <api_key> -l <language> <file>`；另有 `scripts/batch_translate.py` 批量处理目录树。安装脚本（Windows `install.bat`）提供 "install command line only" 选项，可不装 GUI。
  来源：https://github.com/machinewrapped/llm-subtrans （README "Command Line" / "Installing from source" 节）
- **自定义 OpenAI 兼容端点（README 宣称 + 参数证实）**：三条路——(a) 原生 **DeepSeek provider**（`-k/--apikey` 或环境变量 `DEEPSEEK_API_KEY`，`-b/--apibase` 可自定义，默认模型 `deepseek-chat`）；(b) OpenAI provider 的 `-b/--apibase` 指向任意兼容端点；(c) **Custom Server**——"can interface directly with any server that supports an OpenAI compatible API"，`-s` 服务器地址 + `-e` 端点（`/v1/chat/completions` 等）+ `--chat` 会话格式开关。Kimi（`https://api.moonshot.cn/v1`，官方文档确认兼容 OpenAI SDK）走 (b) 或 (c) 均可。
  来源：https://github.com/machinewrapped/llm-subtrans ；https://platform.moonshot.cn/docs/api/chat
- **长 SRT 处理（架构文档证实）**：核心是 **scene（场景）→ batch（批次）** 两级分块——按时间间隙（`--scenethreshold`）切场景，场景内按 `--minbatchsize`/`--maxbatchsize` 分批；每批携带场景级上下文（summary）保证跨批一致性。**断点续翻**：`--project` 写 `.subtrans` 项目文件，中断后重跑同一命令自动续翻（GUI 默认开启，CLI 需显式 `--project`，README 原话 "It is highly recommended"）。
  来源：https://github.com/machinewrapped/llm-subtrans/blob/main/docs/architecture.md ；https://github.com/machinewrapped/llm-subtrans
- **时间戳/对齐保障（文档证实）**：只翻译文本行，时间轴与条目号由解析层原样写回；v0.2 起专门改了 prompting 策略"greatly reduces desyncs caused by GPT merging together source lines"；批次错位会"trigger expensive retries"（自动重试）；`--postprocess` 修复 LLM 字幕常见问题（长行加换行等）。README 同时诚实提示：批次调大"increase the risk of the AI desynchronising"——防护存在但不是绝对保证，参数需在质量与成本间权衡。
  来源：https://github.com/machinewrapped/llm-subtrans （README "Version History" 与 Advanced usage 节）
- **术语表/提示词（参数证实）**：`--terminology "Alice::アリス"`（可重复、可给文件）预置术语映射；`--build-terminology-map` 在翻译过程中累积人名/专名注入后续批次；`--instruction` / `--instructionfile` 自定义系统指令；`--substitution` 译前/译后字符串替换；`--moviename` / `--description` 提供作品上下文。
  来源：https://github.com/machinewrapped/llm-subtrans
- **维护状态（API 核实）**：活跃。最新 release v1.6.1（2026-07-13），2026 年内 v1.5.8 → v1.6.0 → v1.6.1；最近 push 2026-07-22；项目自 2023 年持续演进（原名 gpt-subtrans）。
  来源：https://github.com/machinewrapped/llm-subtrans/releases
- **安装（Windows 可用）**：无 PyPI 包；需 `git clone` + Python 3.10+，`install.bat`（可选 `--portable`）或手动 `pip install -e .`（最小安装即含 CLI + OpenRouter/Custom Server 支持，DeepSeek/OpenAI 等按需加 extras）。比 pip 一键略重，但一次性的。
  来源：https://github.com/machinewrapped/llm-subtrans

### 2.2 rockbenben/subtitle-translator —— 强备选（对齐保障设计最激进）

- **是什么**：1050+ stars 的开源字幕批量翻译工具，本体是浏览器 Web 应用（纯客户端），**附带同引擎 CLI**（README 原话："`yarn cli` runs the same engine, parsers, and cache from a terminal"）。
  来源：https://github.com/rockbenben/subtitle-translator
- **真 CLI（README 证实）**：`yarn cli -i movie.srt -t zh -m deepseek --api-key sk-xxx`；支持多文件、多目标语言一次跑、双语输出、强制格式转换、`--list-methods` / `--help`；退出码规范（0 全成 / 1 部分软失败 / 2 参数错误 / 130 取消）。配置可复用 Web UI 导出的 settings JSON（keys、prompts、glossary 一次配置两端通用）。
  来源：同上 README "Command Line" 节
- **自定义端点（README 证实）**：27 家 LLM 提供商/网关，**DeepSeek 与 Moonshot (Kimi) 均为内置一等选项**，另有 "Custom (OpenAI-compatible)" 端点（Ollama / LM Studio / vLLM 等）。
  来源：同上 README "Translation APIs" 节
- **长 SRT 处理（README 证实）**：分块压缩 + 并行处理（宣称约 1 秒/集）；上下文感知翻译——`Concurrent Lines`（并行翻译行数，默认 20）与 `Context Lines`（每批上下文行数，默认 50）可调；**逐行缓存断点续翻**（"every translated line is cached, so re-running after a Ctrl-C … only pays for what is still missing"，缓存文件 `~/.translate-cli-cache.json`）。
  来源：同上
- **时间戳/对齐保障（README 证实，设计级）**：**时间码、序号、ASS 头在本地剥离，模型只看到对话文本**——"the timeline physically cannot be touched"，这是所有候选里最彻底的对齐保障（其他工具靠 prompt + 校验防错位，它从结构上消除错位的"时间轴"维度；条目级的合并/拆行风险仍存在，README 提示 70B 以下模型在 context 模式可能错位，建议用主流大模型）。
  来源：同上 README "Structural Separation" 与 FAQ 节
- **术语表/提示词**：支持自定义 system/user prompts + 温度；glossary 写在 System Prompt 里（FAQ 明示做法 "Keep verbatim: iPhone, OpenAI, John Smith"），全季共享同一上下文保证跨集一致。无独立的结构化术语表参数。
  来源：同上
- **维护状态（API 核实）**：活跃。最新 release v3.1.0（2026-08-23），最近 push 2026-08-24；2025-03 创建以来高频迭代。
  来源：https://github.com/rockbenben/subtitle-translator/releases
- **安装（Windows 可用但偏重）**：**CLI 不在 npm 上单独发行**，需 `git clone` + Node.js ≥ 20.9 + Yarn（`yarn install` 装整个 Next.js 应用的依赖）后 `yarn cli`。对本仓库"命令可文档化复现"的目标是合格的（命令固定），但安装体积比一个 pip 包大。
  来源：同上 README "Run It Yourself" 节

### 2.3 VideoCaptioner CLI（WEIFENG2333/VideoCaptioner）—— 安装最省事的可用项

- **是什么**：15.8K stars 的中文字幕全流程工具，v1.4 起重构出独立 CLI（PR #1043），PyPI 直接安装（最新 1.4.2，2026-05-24 上传）。
  来源：https://github.com/WEIFENG2333/VideoCaptioner/pull/1043 ；https://pypi.org/project/videocaptioner/
- **真 CLI（官方 CLI 文档证实）**：`videocaptioner subtitle input.srt --translator llm --target-language zh-Hans --api-key ... --api-base ... --model ...`；配置优先级"命令行 > 环境变量 > 配置文件"，支持 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` 环境变量与 TOML 配置文件；有退出码规范和 `doctor` 环境诊断（`--json` 输出，CI 友好）。
  来源：https://github.com/WEIFENG2333/VideoCaptioner/blob/master/docs/cli.md
- **自定义端点（文档证实）**：LLM 翻译器基于 litellm 调 OpenAI 兼容 API（模块文档原话 "使用 litellm 直接调用 OpenAI 兼容 API"），`--api-base` 任意填，DeepSeek / Kimi 均可。
  来源：https://github.com/WEIFENG2333/VideoCaptioner/blob/master/docs/dev/translate-module.md
- **长 SRT 处理（源码证实）**：批量分块（`batch_num`）+ 多线程并发（`thread_num`）；**内置缓存机制**（按原文+目标语言+模型+prompt 哈希缓存翻译结果，重跑不重复扣费）；**对齐防护在源码中可见**：发给 LLM 的是按条目 index 做 key 的 JSON 字典，`_validate_llm_response` 校验返回，失败进入 agent loop 把错误回喂模型要求"output ONLY a valid JSON dictionary with ALL N keys"，再失败降级为逐条翻译（`_translate_chunk_single`）。
  来源：https://github.com/WEIFENG2333/VideoCaptioner/blob/master/docs/dev/translate-module.md ；https://github.com/WEIFENG2333/VideoCaptioner/blob/master/videocaptioner/core/translate/llm_translator.py
- **关键坑（文档证实，必须注意）**：`subtitle` 命令**默认开启"断句"（LLM 按语义重组条目）和"优化"（修 ASR 错误）**——两者都会改变条目内容/数量。本流程是"whisper 已产出 SRT，只要翻译"，必须显式加 `--no-split --no-optimize` 才是纯翻译，否则输出条目结构不再一一对应（虽然时间轴仍是合法的）。另有 `--reflect` 反思式翻译（质量更高更慢）、`--prompt` 自定义提示词。
  来源：https://github.com/WEIFENG2333/VideoCaptioner/blob/master/docs/cli.md
- **术语表**：无独立术语表参数，只有 `--prompt` 自定义提示词（可手写专名对照进去）。此项弱于 LLM-Subtrans。
  来源：同上
- **维护状态（API 核实）**：活跃。最近 push 2026-07-19，GitHub release v1.4.2（2026-05-24）。CLI 形态本身较新（v1.4 引入），成熟度不如其 GUI。
  来源：https://github.com/WEIFENG2333/VideoCaptioner/releases

### 2.4 oalieno/subab —— 设计精良但零关注度的新项目

- **是什么**：单文件 Python CLI（`subab.py`），自我定位为"llm-subtrans 的轻量替代品"，专为 OpenAI 兼容 API 设计（`--api-base` / `--api-key` / `--model` 为必填参数），面向 Bazarr 自动化集成。
  来源：https://github.com/oalieno/subab
- **对齐保障（README 证实，设计有意思）**：**每行注入 ID 标签**（`--tag-mode opaque/numeric`，如 `aa11|`）强制 1:1 映射，防合并/拆行；少一行的典型合并错误做局部重试修复；**Adaptive Batching**——批次失败就二分缩小递归重试（128→64→32），自动找到模型能稳定处理的最大批次。卡拉 OK 密行段有专门策略（remove/skip/translate）。
  来源：同上 README
- **术语表**：`--glossary-dir`（global + 按剧集目录名加载）+ `--auto-glossary`（首次翻译自动生成术语表供后续集复用）。
  来源：同上
- **维护/风险（API 核实）**：2025-10 创建，最近 push 2026-08-27，**0 stars 单维护者**。设计文档写得很内行，但无社区验证、无打包发行（`uv sync` 跑源码），作为流程标准工具风险偏高；其 ID 标签思路值得借鉴。
  来源：https://github.com/oalieno/subab

### 2.5 vkastrup/sub-translator —— 另一个新项目，面向影视交付

- **是什么**：CLI + DaVinci Resolve 插件，支持 13 种字幕格式读写（SRT/VTT/ASS/TTML/SCC 等），"Timings are never touched. Only the text changes"；批次翻译时每批携带前几条已译文做上下文；**错位防护宣称**："the tool will retry and subdivide a batch rather than hand back a file that has drifted out of sync"。
  来源：https://github.com/vkastrup/sub-translator
- **自定义端点**：`custom` provider（`SUBTRANS_API_KEY`）接"any OpenAI-compatible endpoint"；内置 mistral/claude/groq/openrouter/ollama。有 `--glossary terms.json` 结构化术语表。
  来源：同上
- **维护/风险（API 核实）**：**2026-07-22 才创建，0 stars**，单人项目；面向短视频广告交付场景。活跃但同样未经社区验证，且 install.sh 为 Unix 脚本（Windows 需手动建 venv）。
  来源：同上

### 2.6 azratul/llm-subs —— 走 agent CLI 路线的特殊形态

- **是什么**：通过 LLM 的 **agent CLI**（`claude` / `codex` / `antigravity` / `opencode`）或 Ollama / LiteLLM 做翻译的 CLI 工具。设计上同样做了 ID 标注往返（模型只见 `[ID] Speaker: text`）、ASS 样式块还原、per-series 记忆（人名/性别/称谓跨集一致）。
  来源：https://github.com/azratul/llm-subs ；https://pypi.org/project/llm-subs/
- **对本流程的适配**：DeepSeek/Kimi 理论上可经 LiteLLM provider 接入，但主路径是订阅制 agent CLI，与"OpenAI 兼容端点 + 按量 API"的预期形态不同；3 stars、2026-06 新建。记录为可关注项，不做候选。
  来源：同上

### 2.7 gemini-srt-translator（MaKTaiL）—— 成熟但锁定 Gemini，不合格

- CLI 做得很完整（`gst translate`、断点续翻 `--start-line`、batch-size/context-size 可调、双语、PyPI 安装，348 stars，v3.8.1 / 2026-08-27 极活跃），**但只支持 Google Gemini / Vertex AI，无 OpenAI 兼容端点**——不满足硬性要求 2。社区有 fork（xeonliu/oai-srt-translator，1 stars）改造成 OpenAI 兼容，但未经验证。
  来源：https://github.com/MaKTaiL/gemini-srt-translator ；https://pypi.org/project/gemini-srt-translator/ ；https://github.com/xeonliu/oai-srt-translator

### 2.8 妙幕 SmartSub —— 确认无 CLI（本调研的关键核实点）

- README 全文与文档站无命令行/headless 入口，形态为纯 GUI 桌面应用（下载安装节只提供各平台安装包）。
  来源：https://github.com/buxuku/SmartSub ；https://smartsub.linxiaodong.com/
- **GitHub issue #163「希望添加命令行功能」（2025-04 提出，至今 open）**，作者 buxuku 当日回复："命令行版本请参考这个项目 https://github.com/buxuku/VideoSubtitleGenerator"——即官方层面 CLI 不在 SmartSub 的路线图上。
  来源：https://github.com/buxuku/SmartSub/issues/163
- 而 VideoSubtitleGenerator 是 SmartSub 的前身（README 置顶引导用户移步 SmartSub），翻译仅支持百度/火山/DeepLX/Ollama，**无 OpenAI 兼容 LLM 端点**，不满足要求 2。
  来源：https://github.com/buxuku/VideoSubtitleGenerator
- 结论：SmartSub 继续留在 GUI/校对环节；CLI 场景不要用 SmartSub。

### 2.9 已淘汰/不进场的老工具

- **jesselau76/srt-gpt-translator**（146 stars）：GPT-3.5 时代工具，最后 push 2023-04，配置文件无 base_url 自定义，不符合"活跃"要求。来源：https://github.com/jesselau76/srt-gpt-translator
- 调研中另检出多个 2025 下半年创建的 0–1 star 微型项目（caiquearaujo/subtitle-ai-translator、yanp/ai-subtitle-translator 等），功能描述单薄、无社区验证，不进场详评。来源：https://github.com/caiquearaujo/subtitle-ai-translator ；https://pypi.org/project/ai-subtitle-translator/

## 3. 候选对比表

| 工具 | 真 CLI | OpenAI 兼容端点（DeepSeek/Kimi） | 长 SRT 处理 | 对齐保障 | 术语表/提示词 | 维护状态（核实） | 安装（Windows） |
|---|---|---|---|---|---|---|---|
| **LLM-Subtrans** | 是（`llm-subtrans` + 批量脚本，可装 CLI-only） | 原生 DeepSeek + Custom Server 任意兼容端点 | scene/batch 两级分块 + `--project` 断点续翻 | prompt 防错位 + 错位重试 + postprocess；时间轴由解析层写回 | `--terminology` / `--build-terminology-map` / `--instruction` 全套 | 活跃，v1.6.1 / 2026-07，645 stars | git clone + install.bat / pip -e（无 PyPI 包） |
| **rockbenben/subtitle-translator** | 是（`yarn cli`，同引擎同缓存） | 内置 DeepSeek、Moonshot (Kimi) + Custom OpenAI-compatible | 分块并行 + 逐行缓存续翻（Ctrl-C 友好） | **时间码本地剥离，模型碰不到轴**（结构级）；条目级错位靠模型能力 | system/user prompt 内嵌 glossary；无结构化术语表 | 活跃，v3.1.0 / 2026-08，1063 stars | git clone + Node ≥20.9 + yarn（非 npm 包，偏重） |
| **VideoCaptioner CLI** | 是（6 子命令，退出码/JSON 诊断规范） | `--api-base` 任意兼容端点（litellm） | 分批 + 多线程 + 结果缓存 | index-keyed JSON 校验 + 错误回喂重试 + 逐条降级（源码可见） | 仅 `--prompt`，无结构化术语表 | 活跃，v1.4.2 / 2026-05，15.8K stars（CLI 形态新） | **pip install，最省事** |
| subab | 是（单文件脚本） | 仅 OpenAI 兼容端点（必填参数） | Adaptive Batching 二分降级 | **行级 ID 标签强制 1:1** + 局部修复 | glossary-dir + auto-glossary | 活跃但 0 stars 单人 | uv sync 跑源码，无发行包 |
| vkastrup/sub-translator | 是 | `custom` provider 任意兼容端点 | 分批 + 上下文 | 宣称错位重试/细分，时间轴不动 | `--glossary terms.json` | 2026-07 新建，0 stars | Unix 安装脚本，Windows 需手动 |
| llm-subs | 是 | 主路径 agent CLI；DeepSeek 需绕 LiteLLM | 分批 + per-series 记忆 | ID 往返 + 样式还原 | per-series 记忆文件 | 3 stars，2026-06 新建 | uv tool install（需 agent CLI 或 LiteLLM） |
| gemini-srt-translator | 是（很完善） | **否（锁 Gemini）** | batch + resume | 时间戳保留（宣称） | description 参数 | 极活跃，348 stars | pip install |
| **SmartSub** | **否（GUI-only，issue #163 证实）** | （GUI 内原生支持，不适用） | — | — | — | 活跃 | — |
| VideoSubtitleGenerator | 是 | **否（百度/火山/DeepLX/Ollama）** | — | — | — | 已被 SmartSub 取代 | node/yarn |

## 4. 推荐方案

### 首选：LLM-Subtrans CLI

把翻译步骤固化为一条可文档化的命令（DeepSeek 为例）：

```powershell
# 一次性：git clone + install.bat（选 command line only，按提示填 DEEPSEEK_API_KEY）
# 每次：
llm-subtrans --project -l Chinese input.srt --provider deepseek --model deepseek-chat --build-terminology-map
# 中断后重跑同一命令即续翻；Kimi 则换 Custom Server：
llm-subtrans --project -s https://api.moonshot.cn -e /v1/chat/completions --chat -k <key> -m moonshot-v1-8k -l Chinese input.srt
```

理由：7 条硬性要求全部满足且证据级别最高（架构文档 + 参数文档双重证实）；scene/batch + 项目文件 + 术语映射是为长字幕翻译专门设计的，正好覆盖"千级条目 + 错位 + 续翻 + 专名一致"四个核心风险；三年维护史，不是一次性项目。

### 备选

- **备选 A（对齐焦虑最重时）**：rockbenben/subtitle-translator 的 `yarn cli`——时间轴结构级不可破坏，DeepSeek/Kimi 双原生支持；代价是 Node + 克隆整个 Web 应用仓库。
- **备选 B（安装最省事 / 已装过 VideoCaptioner）**：`pip install videocaptioner` 后 `videocaptioner subtitle input.srt --translator llm --no-split --no-optimize --api-base https://api.deepseek.com/v1 --model deepseek-chat`。**务必加 `--no-split --no-optimize`**，否则默认的断句/优化会改变条目结构。术语一致性需求高时不选它。
- **兜底**：GUI 方案（SmartSub）仍可用；或手动分块粘贴（见原调研第 3 节）。

### 流程衔接

CLI 翻译与原调研其余环节不冲突：whisper-ctranslate2 出原文 SRT → LLM-Subtrans 出中文 SRT → Subtitle Edit 人工抽查/AI Review 校验。SmartSub 退为可选的校对/GUI 工具。校验环节的结论（Subtitle Edit）无需变更。

## 5. 对照评估：若自写，最小可行形态是什么

结论：**不需要自写**（LLM-Subtrans 已合格）。以下为对照估算，供存档：

- **形态**：单个 Python 脚本（约 300–500 行），`srt` 库解析 → 按 N 条/批（或按 token 估算）分块 → OpenAI SDK 调兼容端点（base_url 参数化）→ 以"序号 key 的 JSON"约束输出 → 逐批校验条数 → 失败二分降级重试 → 结果落盘缓存（每批一个 key）实现断点续翻 → 系统提示词注入术语表。
- **工作量量级**：核心 1–2 天；但真正的成本在长尾——错位重试策略、上下文衔接（前几行译文回喂）、限流退避、输出截断处理、ASS/VTT 扩展、批大小调参，这些是 llm-subtrans 用三年版本史（v0.2 防合并 prompt、v0.7 postprocess 等）逐项趟出来的，自写要追平约需数倍时间且需真实语料回归。
- **触发条件**：仅当 LLM-Subtrans 停止维护、或出现其架构无法满足的硬需求（如必须与某个内部系统深度集成）时再考虑；届时 subab 的 ID 标签 + 自适应分批是最值得借鉴的设计。

## 注意事项

- 隐私：所有 API 方案都会把字幕文本发送到供应商服务器（llm-subtrans README 有明示）；敏感内容自行权衡。
- 参数敏感性：批次大小是"速度/成本 vs 错位风险"的旋钮（llm-subtrans README 明示），首次使用建议用 `--maxlines` 小样本试跑再全量。
- 调研基于 2026-08-30 的 GitHub API / PyPI / 官方 README 状态；llm-subtrans 无 PyPI 包这一点若上游改变（发布打包），安装路径可简化。
