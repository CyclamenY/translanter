# SRT 字幕的 LLM 翻译执行方式调研

> 对应 issue：#3「LLM 翻译的执行方式：现成字幕翻译工具调研」
> 调研日期：2026-08-30（覆盖各工具截至 2025–2026 年的状态）
> 问题：不写代码，如何把 whisper 产出的 SRT 喂给 LLM API，拿回时间轴与条目一一对应的中文字幕 SRT？LLM 供应方预期为 DeepSeek（OpenAI 兼容 API）。

## 结论速览

现成工具已经成熟，**不需要写任何代码**。首选 **妙幕（SmartSub）**（原生支持 DeepSeek、有术语表与"译文错位防护"、可直接批量翻译已有 SRT），编辑器/校验环节用 **Subtitle Edit**（自带 OpenAI 兼容翻译引擎 + AI Review 校对功能）。兜底方案：把 SRT 分块手动粘贴进 DeepSeek 网页聊天——1 小时视频约 3–5 块，可忍受；3 小时视频约 10–15 块，勉强可行但易出错，建议只在工具链失效时用。

---

## 1. 严肃候选工具详评

### 1.1 妙幕 SmartSub（buxuku/SmartSub）—— 首选

- **是什么**：开源跨平台桌面应用（Windows/macOS/Linux），覆盖「语音转写 → 字幕翻译 → 校对润色 → TTS 配音 → 烧录」全流水线，也可单独"翻译已有字幕"批量处理现成 SRT。
  来源：https://github.com/buxuku/SmartSub ；https://smartsub.linxiaodong.com/features/subtitle-translation
- **DeepSeek / 自定义 OpenAI 兼容端点**：原生一等支持。翻译页内置「深度求索」服务商，默认 API 地址 `https://api.deepseek.com/v1`、模型 `deepseek-chat`，只需填 API Key；另有「自定义 OpenAI 兼容 API」类别可接任意 OpenAI 风格端点（Kimi 等同理）。
  来源：https://smartsub.linxiaodong.com/guides/translation/deepseek ；https://smartsub.linxiaodong.com/guides/translation/overview
- **长 SRT 处理**：批量分块翻译，支持"批量翻译数量 / 批次并发数"调节、术语表（命中词条自动注入提示词）、自定义系统/用户提示词模板；v3.5 起内置多层"对齐防护"自动修复译文错位，另可开启「回显对齐校验」。
  来源：https://smartsub.linxiaodong.com/guides/translation/deepseek ；https://smartsub.linxiaodong.com/advanced/custom-prompts ；https://smartsub.linxiaodong.com/faq
- **时间戳**：翻译只替换文本行，输出纯译文或双语字幕，时间轴不变（"对齐防护"正是为防止条目错位而设）。来源：同上 FAQ。
- **费用**：软件免费开源；DeepSeek API 按量计费（官方文档原话："充值少量金额（几块钱可以翻很多字幕）"）。来源：https://smartsub.linxiaodong.com/guides/translation/deepseek
- **维护状态**：活跃。2025–2026 年发布 3.0 大版本（多引擎转写、GPU 加速、UI 重做）及 3.5（对齐防护）。来源：https://github.com/buxuku/SmartSub/releases
- **附带收益**：内置 Whisper/FunASR 本地转写（支持 GPU），与本仓库的转写步骤可合并；也有校对润色环节，可部分覆盖"校验"步骤。

### 1.2 Subtitle Edit —— 编辑器 + 翻译 + AI 校验三合一

- **是什么**：Windows 原生、免费开源、维护十余年的字幕编辑器（当前 5.x；4.0.x 系列在 2025 年持续更新，如 4.0.12 增加 Mistral/KoboldCpp 等 AI 翻译引擎）。
  来源：https://www.nikse.dk/subtitleedit ；https://github.com/SubtitleEdit/subtitleedit/blob/main/Changelog.txt ；https://www.nikse.dk/posts/4d48601d-699a-4404-beea-34c904c5580b
- **DeepSeek / 自定义端点**：Auto Translate 的引擎列表包含 "ChatGPT" 和 **"OpenAI Compatible API"**（官方文档定义："Generic engine for any service exposing an OpenAI-compatible chat/completions endpoint"）；其 AI Review 文档明确把 DeepSeek 列为可接的云服务之一（"cloud APIs (OpenAI, Groq, OpenRouter, DeepSeek, Mistral, Gemini)"，填 URL、模型名、API Key 即可）。
  来源：https://subtitleedit.github.io/subtitleedit/features/auto-translate.html ；https://subtitleedit.github.io/subtitleedit/features/ai-review.html
  注意：社区有 issue 指出自定义 OpenAI 兼容端点在模型列表等方面曾有兼容性限制，接入 DeepSeek 时建议先用小文件验证（https://github.com/SubtitleEdit/subtitleedit/issues/10054）。
- **长 SRT 处理**：逐条/分批自动翻译；"Advanced Local Engines"（llama.cpp、Ollama）支持带上下文、剧情摘要（synopsis）、术语表（glossary）的批量翻译，"giving more consistent names, pronouns, and terminology than line-by-line translation"。来源：https://subtitleedit.github.io/subtitleedit/features/auto-translate-advanced.html
- **时间戳**：编辑器本体就是围绕时间轴工作的，翻译仅替换文本，条目结构无损。
- **校验步骤的加成**：内置 **AI Review**——用 LLM 对字幕做校对审阅，正好覆盖本流程的"AI 校验"步骤；另有 Copy/Paste Translate（半自动的复制粘贴翻译工作流，见第 3 节）。
  来源：https://subtitleedit.github.io/subtitleedit/ ；https://subtitleedit.github.io/subtitleedit/features/ai-review.html
- **费用/维护**：免费开源，维护极活跃；无论如何它大概率都是流程里人工抽查/修轴环节的编辑器，顺手可承担翻译。

### 1.3 LLM-Subtrans（machinewrapped/llm-subtrans，原名 gpt-subtrans）—— 最强备选

- **是什么**：开源（约 600+ stars）的专用字幕 LLM 翻译器，支持 SRT / SSA·ASS / VTT，提供 CLI（`llm-subtrans.py`）与 GUI（`gui-subtrans.py`），Python 编写。
  来源：https://github.com/machinewrapped/llm-subtrans
- **DeepSeek / 自定义端点**：**原生 DeepSeek provider**（`-k/--apikey` 或环境变量 `DEEPSEEK_API_KEY`，`-b/--apibase` 可指向自定义部署）；另有 OpenAI（可设 api_base）、OpenRouter、Gemini、Anthropic、Mistral，以及 "Custom Server"——"can interface directly with any server that supports an OpenAI compatible API, including locally hosted models e.g. LM Studio"。
  来源：https://github.com/machinewrapped/llm-subtrans ；https://deepwiki.com/machinewrapped/llm-subtrans/4.5-deepseek
- **长 SRT 处理**：架构核心是 **scene（场景）→ batch（批次）** 两级分块，带项目文件（可中断续翻），场景级上下文保证术语一致性；批大小可调。
  来源：https://github.com/machinewrapped/llm-subtrans/blob/main/docs/architecture.md ；https://github.com/machinewrapped/llm-subtrans/tree/main/PySubtrans
- **时间戳**：解析字幕格式后只翻译文本行，时间轴与条目号原样写回；DeepWiki 对 DeepSeek provider 的评价是"translation is not its primary strength"（指模型本身非翻译专用，属主观评价）。
  来源：https://deepwiki.com/machinewrapped/llm-subtrans/4.5-deepseek
- **费用/维护**：免费开源；README 明确提示字幕会发送到供应商服务器，隐私政策适用。适合想要 CLI、想把翻译步骤脚本化串进流程的场景（注意：本仓库约定不写新软件，但直接调用现成 CLI 属于"使用工具"，合规）。

### 1.4 VideoCaptioner 卡卡字幕助手（WEIFENG2333/VideoCaptioner）—— 中文社区热门一体化

- **是什么**：基于 LLM 的字幕全流程工具（语音识别、智能断句、校正、翻译、视频合成），约 14K stars，有 Windows GUI 安装包、CLI（PyPI `videocaptioner`）和 Docker 部署。
  来源：https://github.com/WEIFENG2333/VideoCaptioner ；https://pypi.org/project/videocaptioner/
- **自定义端点**：支持。CLI 配置 `videocaptioner config set llm.api_base <url>` / `llm.api_key`；Docker 用 `OPENAI_BASE_URL` / `OPENAI_API_KEY` 环境变量；官方配置教程以国内厂商（SiliconFlow）和中转站为例，DeepSeek 的 OpenAI 兼容端点可直接填入。
  来源：https://github.com/WEIFENG2333/VideoCaptioner ；https://github.com/WEIFENG2333/VideoCaptioner/blob/a52f2edf56ac434c856f18d7da1438edff86552c/docs/llm_config.md
- **长 SRT 处理**：AI 字幕多线程优化与翻译，自带断句/校正（对 whisper 输出的碎句很友好）；默认翻译引擎是微软翻译，文档建议改用大模型翻译。
- **时间戳**：产出带时间轴的 SRT/ASS，翻译不改轴。
- **维护**：2025–2026 年持续更新（v1.4.x，14K stars）。若希望"转写+断句+翻译"一个工具搞定，它是妙幕之外的中文圈主流选择。

### 1.5 Chenyme-AAVT / Srtranslate —— 可关注但非首选

- **Chenyme-AAVT**（约 3K stars，Streamlit 应用）：whisper 识别 + 多 LLM（GPT/Gemini/Claude/零一万物等）翻译 + 字幕合并的全自动视频翻译，支持本地 LLM 与自定义提示词、双语字幕。功能全但偏重"从视频开始的一站式"，且 Streamlit 形态对长视频批处理不如桌面/CLI 工具稳。来源：https://github.com/chenyme/Chenyme-AAVT
- **Srtranslate**：同一作者的新项目，专门的 AI SRT 翻译 Web 应用（Next.js + Flask，站点 srt.chenyme.com），主打语境理解、术语库、翻译记忆。作为托管/自建 Web 服务形态，适合未来"给他人用"的阶段再评估。来源：https://github.com/chenyme/Srtranslate

### 1.6 商业/云服务类（中文社区常用，均不适合本流程主线）

- **剪映专业版**：内置"识别字幕 + 翻译"可做双语字幕，但**翻译是 VIP 付费功能**，云端处理，无法自选 LLM、无术语表，长视频受限于剪辑工程而非 SRT 文件流。来源（社区教程，非官方定价页，注意时效）：https://zhuanlan.zhihu.com/p/702268842 ；https://zhuanlan.zhihu.com/p/687694980
- **网易见外**：曾是国内 UP 主常用的免费转写+翻译平台，**2020 年 3–4 月已暂停对外开放工作台**；现 sight.youdao.com 转向 B 端付费服务（机器+人工英译中约 ¥32/分钟）。来源：https://www.jiemian.com/article/4099752.html ；https://sight.youdao.com/price
- **讯飞听见**：录音/实时转写浏览免费，但**转文字与翻译结果的导出收费**，需购时长卡；按 APP 形态按分钟计费，不适合"本地 SRT → 中文 SRT"的文件流。来源：https://www.iflyrec.com/zhuanxie/64d59281.html

## 2. DeepSeek 兼容性核实

DeepSeek API 官方确认"uses an API format compatible with OpenAI"，`base_url = https://api.deepseek.com`，任何兼容 OpenAI 客户端的软件均可接入——上述 1.1–1.4 四个工具全部满足。
来源：https://api-docs.deepseek.com/

价格（截至调研日，官网为准）：历史上 `deepseek-chat`（64K 上下文、最大输出 8K）输入约 $0.27/1M tokens（cache miss），命中缓存 $0.07/1M；当前官网已迭代到 V4 系列（1M 上下文、峰谷分时计价，缓存命中低至 $0.007/1M 级别）。
来源：https://api-docs.deepseek.com/quick_start/pricing/ （历史存档：https://archive.ph/P7zsY ；https://archive.ph/BGgJ7）
量级估算：1 小时视频字幕约 1–2 万输入 tokens + 2–3 万输出 tokens，单部影片翻译成本在**人民币一角钱量级**，成本不构成选型因素。（估算方法见第 3 节，标注为推算。）

## 3. 低技术兜底评估：手动粘贴 SRT 到 LLM 聊天 UI

**Token/分块估算（推算，非引用）**：正常语速约 130–160 词/分钟，1 小时视频 ≈ 8,000–10,000 英文词 ≈ 700–1,100 条字幕。按英文 ≈ 0.75 词/token，纯文本 10–13K tokens；加上 SRT 序号与时间轴开销（约 +30–40%），**每小时约 13–18K tokens**。

- **1 小时视频**：按每块 4–6K tokens 粘贴（给模型留足输出余量），约 **3–5 块**。在 DeepSeek 网页版（支持文件上传与长上下文）一次对话内可完成，操作约 15–30 分钟，**可忍受**。
- **3 小时视频**：约 **10–15 块**。问题显著：手工分块易弄乱序号/时间轴；跨块术语与译名一致性无人保证；`deepseek-chat` 单次输出上限 8K tokens，长块会被截断；人工校对粘贴结果的时间可能超过工具方案全程。**勉强可行，不推荐作为常态**。
- **增效**：Subtitle Edit 内置 **Copy/Paste Translate** 功能，把"切块→粘贴→回收译文"半自动化，是手动兜底的最舒适形态。来源：https://subtitleedit.github.io/subtitleedit/ ；社区实践（SE 讨论区 #9288，用户导出纯文本分块喂 LLM）：https://github.com/SubtitleEdit/subtitleedit/discussions/9288

## 4. 对比表

| 工具 | 自定义 OpenAI 兼容端点 / DeepSeek | 长 SRT（千级条目）处理 | 时间戳保留 | 校验支持 | 费用 | 维护状态 | 形态 |
|---|---|---|---|---|---|---|---|
| **妙幕 SmartSub** | 原生 DeepSeek 服务商 + 任意 OpenAI 兼容 API | 批量分块 + 并发 + 术语表 + 对齐防护（v3.5） | 是（纯译文/双语输出） | 内置校对润色环节 | 软件免费，API 按量（几块钱量级） | 活跃（3.0/3.5，2025–26） | Windows/mac/Linux 桌面 |
| **Subtitle Edit** | "OpenAI Compatible API" 引擎，文档明示可接 DeepSeek | 自动逐条/批量翻译；高级引擎带 synopsis+glossary | 是（编辑器本体） | **AI Review**（LLM 校对）+ Fix Common Errors | 免费开源 | 极活跃（5.x，2025–26） | Windows 桌面 |
| **LLM-Subtrans** | 原生 DeepSeek provider + Custom Server | scene/batch 两级分块，项目文件可续翻 | 是 | 无内置校对（靠二次调用） | 免费开源 | 活跃（~600 stars） | CLI + GUI（Python） |
| **VideoCaptioner** | `llm.api_base` / `OPENAI_BASE_URL` 自定义 | 多线程翻译 + 断句/校正一体化 | 是 | 内置校正（偏断句/错字） | 免费开源 | 活跃（14K stars） | Windows GUI / CLI / Docker |
| Chenyme-AAVT / Srtranslate | 多 LLM、可自定义 | 批处理一般（Streamlit）/ Web 服务形态 | 是 | 无（AAVT 校对功能在 TODO） | 免费开源 / 托管站 | 中（AAVT 3K stars） | Streamlit / Web |
| 剪映专业版 | 否（云端黑盒，不可选模型） | 云端处理 | 是 | 无 | 翻译需 VIP 付费 | 商业产品 | 桌面剪辑软件 |
| 网易见外 | —（免费工作台 2020 年已关闭） | — | — | — | B 端 ¥32/分钟级 | 转型 B 端 | 云服务 |
| 讯飞听见 | 否 | 上传音频云端处理 | 是 | 无 | 导出收费（时长卡） | 商业产品 | APP/云服务 |
| 手动粘贴聊天 UI | 天然支持（网页版免费） | 1h 约 3–5 块可忍受；3h 约 10–15 块易错 | 依赖模型不破坏格式（有风险） | 可另开对话让 AI 校对 | 免费（网页版额度） | — | 浏览器 |

## 5. 推荐方案

### 首选：妙幕 SmartSub 负责"翻译"，Subtitle Edit 负责"校验 + 人工抽查"

1. whisper 产出原文 SRT（流程既有步骤）。
2. **妙幕 SmartSub** →「翻译已有字幕」：服务商选「深度求索」（默认 `https://api.deepseek.com/v1`，模型 `deepseek-chat`），开启术语表（人名/专有名词一致性）与回显对齐校验；输出纯中文 SRT（或双语 SRT 便于校对）。
   依据：唯一一个把 DeepSeek 作为一等公民、且针对"译文错位"这个 LLM 字幕翻译最大坑做了多层防护的开源工具；中文文档；可直接吃现成 SRT，不强制捆绑它的转写模块。
   来源：https://smartsub.linxiaodong.com/guides/translation/deepseek ；https://smartsub.linxiaodong.com/features/subtitle-translation
3. **Subtitle Edit** 打开译文 SRT：用 **AI Review**（OpenAI 兼容端点指向 DeepSeek）做 AI 校验，再人工抽查中文通顺度。
   来源：https://subtitleedit.github.io/subtitleedit/features/ai-review.html
4. 若想少装一个工具：妙幕/SmartSub 或 VideoCaptioner 也可合并"转写"步骤（自带 whisper 系），留待转写 issue 决策。

### 备选 / 兜底

- **备选 A（想脚本化/CLI 串联）**：LLM-Subtrans CLI，原生 DeepSeek provider，scene/batch 分块 + 项目续翻，适合把翻译步骤固化成一条命令。来源：https://github.com/machinewrapped/llm-subtrans
- **备选 B（已重度使用 Subtitle Edit）**：直接用 SE 的 Auto Translate "OpenAI Compatible API" 引擎接 DeepSeek，一工具完成翻译+校验；先小样本验证兼容性（见 issue #10054）。
- **兜底（所有工具失效/零安装）**：Subtitle Edit 的 Copy/Paste Translate 或手动把 SRT 分块粘贴进 DeepSeek 网页版；1 小时视频 3–5 块可忍受，3 小时视频 10–15 块仅作应急，务必逐块核对条目数与序号连续性。

### 注意事项

- 隐私：所有 API 方案都会把字幕文本发送到供应商服务器（llm-subtrans README 亦有明示）；敏感内容需自行权衡。
- 一致性：长视频务必使用术语表/glossary 类功能，否则跨块译名漂移是主要质量风险。
- 调研基于 2026-08 的官网/仓库状态；DeepSeek 型号与定价迭代快（已进入 V4、1M 上下文、峰谷计价），执行前以 https://api-docs.deepseek.com/quick_start/pricing/ 实时页为准。
