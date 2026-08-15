## Agent skills

## Development principles

- 以开发可实际使用的完整产品为目标，不以最小依赖或最小实现为项目原则。
- 围绕用户工作流补齐必要的后端、前端、状态反馈和异常处理；成熟依赖能明显提升质量或交付效率时可以引入。
- 保持改动聚焦当前需求，避免与可用性无关的重构和过度设计。

### Issue tracker

Issues and specs live as local Markdown under `.scratch/`.
See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default labels: `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, and `wontfix`.
See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo. Read `CONTEXT.md` and relevant ADRs under
`docs/adr/`.
See `docs/agents/domain.md`.
