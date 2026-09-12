## Agent skills

## Development principles

- 以开发可实际使用的完整产品为目标，不以最小依赖或最小实现为项目原则。
- 围绕用户工作流补齐必要的后端、前端、状态反馈和异常处理；成熟依赖能明显提升质量或交付效率时可以引入。
- 保持改动聚焦当前需求，避免与可用性无关的重构和过度设计。
- 给改进建议时停在现有产品边界内：以 spec 的 Out of Scope、ADR 和 `CONTEXT.md` 为准。优先收口已有对象（资料、会话、蓝图、试卷、作答、错题），不要为对齐 NotebookLM / Quizlet / Anki 而新开闪卡、间隔重复引擎、题库或向量库。
- 声明生态位内的功能闭环已收口。默认只修打断现有闭环的缺陷，不为竞争力或宣传加功能。下一输入是真实使用中的卡点。出处对准、默认出卷路径、本机模型入门等卖点加码已讨论并搁置，除非使用者明确要求。

### Research

同类产品调研必须同时看商业产品官方文档和 GitHub 开源同类。开源侧用 `gh search repos`、`gh repo view` 读 README 和仓库范围，不要只靠评测博客。

过程性调研写在 `docs/research/`，默认不入库（见 `.gitignore`）。已被 spec 或 ADR 引用的结论才 `git add -f`。已经跟踪的文件不要 `git rm`。

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
