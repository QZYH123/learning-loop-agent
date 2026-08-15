# AI 网页端资料与会话管理参考

**调研日期:** 2026-08-15
**主要参考:** Google 官方 Gemini Notebook Help

## 结论

本项目应把“科目空间”做成资料、聊天和学习产物的容器，但把三者分开管理：

- 资料库保存用户资料、来源位置和资料状态。
- 聊天记录是问答 Agent 的一等数据，完整保存，并记录当条消息使用的模型配置。
- 试卷、笔记、章节提纲等是独立学习产物，能回链到资料和相关聊天，但不把产物混进原始聊天文本。
- AI 回答必须带来源引用；用户能查看引用原文并跳转到对应位置。
- 删除或失效的资料不应静默改写历史聊天和已保存试卷；后续检索停止使用该资料，并明确显示来源不可用。

## NotebookLM 的可借鉴做法

### 资料空间隔离

官方文档把 Notebook 定义为特定项目的资料集合，并明确不同 Notebook 之间不会互相访问资料。资料面板支持逐个勾选或取消资料，控制当前回答使用哪些来源。

来源：

- [Create a notebook in Gemini Notebook](https://support.google.com/gemininotebook/answer/16206563?hl=en)
- [Add or discover new sources for your notebook](https://support.google.com/gemininotebook/answer/16215270?hl=en)

对本项目的采用：科目空间之间默认隔离；一次会话或一次组卷可以选择该科目下的资料子集。

### 聊天记录与引用

NotebookLM 官方说明聊天记录会保留且对用户私密，并提供清除聊天记录的入口。回答可以使用来源中的直接引文、文本和图片作为引用；用户可以查看引用内容并跳转到来源位置。

来源：

- [Use chat in Gemini Notebook](https://support.google.com/gemininotebook/answer/16179559?hl=en)

对本项目的采用：聊天记录默认完整保存；每条回答记录使用的模型、资料版本、引用位置和请求状态。引用不是装饰，而是回答能否复查的组成部分。

### 资料状态与同步

NotebookLM 对 Google Drive 来源支持自动同步；如果原文件被删除或失去访问权限，来源会变为不可用，并且不会继续被聊天或 Studio 使用。官方还明确说明，NotebookLM 的查看器可能为了分析而改变原始文件的显示方式，但不会修改原文件。

来源：

- [Add or discover new sources for your notebook](https://support.google.com/gemininotebook/answer/16215270?hl=en)

对本项目的采用：保存资料版本和状态（可用、解析中、失败、不可用）；资料失效只影响新的检索，不回写历史产物，也不修改用户原文件。

### 聊天与学习产物分离

NotebookLM 将 Chat 和 Studio 分开。Studio 产物包括笔记、报告、测验等；聊天回答可以保存为笔记，笔记可以继续转成来源。导出到 Docs 或 Sheets 是一次性复制，导出文件的修改不会同步回 NotebookLM。

来源：

- [Create a notebook in Gemini Notebook](https://support.google.com/gemininotebook/answer/16206563?hl=en)
- [Create & add notes in Gemini Notebook](https://support.google.com/gemininotebook/answer/16262519?hl=en)

对本项目的采用：试卷和学习笔记作为独立产物保存，保留来源和生成上下文；导出 PDF、Markdown 或文档是明确的导出副本，不承诺双向同步。

## 不照搬的部分

- NotebookLM 的联网搜索、Deep Research、多人共享和云端同步不属于当前单用户本地 MVP。
- NotebookLM 的来源上限和具体文件大小不直接作为本项目的性能承诺；本项目应通过实际资料规模测试后再定限制。
- “来源严格回答”适合本项目的资料依据模式，但用户主动开启补充通用知识时需要清楚标注两种内容的边界。
