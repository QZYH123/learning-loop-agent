# 28 — 试卷导出与打印前端收口

**Type:** task

**Status:** resolved

**Source:** Issue 26 拆票顺序第 2 项，收口 Issue 14 前端。spec 49–50：网页/打印/PDF 版式一致，导出答案版必须明确选择。

## 问题

后端统一渲染与导出已完整：`GET /api/exams/{exam_id}/render-document?edition=...`、`POST /api/exams/{exam_id}/exports`（异步 operation）、`GET /api/exports/{id}` 与 `/file`（PDF、Markdown）。前端没有任何打印或下载入口（`printer`、`download` 图标在 `icons.js` 里未使用）。这是 spec 对「试卷」定义的一部分，不是锦上添花。

## 范围

做：组卷区已发布试卷的打印视图与 PDF / Markdown 导出。
不做：作答复盘导出、批量导出、自定义排版选项、导出与应用内容的双向同步（Out of Scope 已定）。

## 设计规定

- 入口：组卷区试卷标题栏的「更多」菜单内加三项：「打印」「导出 PDF」「导出 Markdown」。守布局规范（标题栏一个主操作 + 最多三个常用图标），不新增独立按钮。
- **版别选择**：三个入口点击后都先弹应用内单选弹窗：「题目版」（默认选中）/「答案版」，弹窗内一句说明「答案版包含答案与解析」。答案版必须用户明确点选，不能默认（spec 50）。
- 打印：新开窗口（或隐藏 iframe）加载 `render-document` 数据，**复用现有题目渲染函数（`solution.js` 与试卷渲染），不得新写第三套题目 HTML**（Issue 26 冗杂 #9）；样式走 `styles.css` 的 `@media print` 或独立 print 样式块，然后 `window.print()`。
- 导出：`POST exports` → 复用现有 operation 轮询机制 → 完成后自动触发 `GET /api/exports/{id}/file` 下载（`Content-Disposition` 已带文件名）。失败走 toast。
- `edition` 取值沿用后端 `ExamEdition` 枚举既有值，前端不得自造字符串。
- `api.js` 补 `getExamRenderDocument`、`createExamExport`、`getExamExport`、`downloadExamExport` 封装，命名与现有函数风格一致。

## 验收标准

1. 已发布试卷可从界面打印（打印预览中题目顺序、编号、选项与网页一致，题目版不含答案与解析）。
2. 导出 PDF / Markdown 各自成功下载；答案版仅在明确选择后生成。
3. 生成中有状态反馈（复用忙碌指示/toast），失败可重试。
4. 全量 pytest 通过；没有新增题目渲染分叉（静态断言打印路径引用 `solution.js` 或既有渲染函数）。

## 测试要求

- 后端不动（已有导出测试）；前端静态断言入口、edition 弹窗、api 封装存在。
- 手工核查一次打印预览的分页与公式渲染（KaTeX），记录在本票 Comments。

## Comments

- 2026-08-20：Issue 27 已验收，按顺序开工本票。后端导出/渲染接口已完整，本票只做前端收口。

## Answer

已落地。组卷试卷标题栏「更多」菜单含打印 / 导出 PDF / 导出 Markdown。三者都先弹版别单选，默认题目版（`questions`），答案版需点选。打印走 `getExamRenderDocument` + 既有 `renderExamQuestion`（`renderBlocks` / `renderOptions` / `renderSolution`）。导出走 `createExamExport` → `pollOperation` → blob 下载。全量 pytest 123 passed。手工打印预览分页/KaTeX 未在本轮做。
