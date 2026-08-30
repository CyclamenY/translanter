# translanter

## 主工作流

用户要求处理视频（转写/翻译/加字幕）时，走主工作流：权威文档 `docs/workflows/video-to-chinese-srt.md`，激活入口 `.pi/skills/process-video/`，LLM 环节用 `.pi/agents/` 下的 subtitle-resegment / subtitle-translator / subtitle-auditor 三个 subagent。

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default canonical labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
