# 39 — 试卷导出核对公式、表格和图片

**Type:** task

**Status:** resolved

**Source:** spec 49–50 与 Issue 28。导出入口已有，当时未核对公式、表格、图片在题目版/答案版里是否同序、答案版是否显式才含解析。

## 范围

做：用带 LaTeX、表格、图片的试卷走渲染文档、Markdown、PDF，断言题目版不含解析、答案版含解析、三种块都还在。
不做：新导出格式、自定义排版、浏览器打印对话框自动化。

## 验收标准

1. `render-document` 题目版与答案版题序一致；题目版 `solution` 为 null。
2. Markdown 题目版含公式和表格，不含「答案与解析」；答案版含解析。
3. 两种 edition 的 PDF 都是合法 PDF，能抽出公式原文和表头。
4. 打印路径继续复用 `renderBlocks`（含 KaTeX 样式）。

## Answer

现有渲染/导出管线已能保留 LaTeX、表格、图片，题目版不含解析。补了带这三种块的回归：`render-document` 题序与 edition、Markdown/PDF 题目版与答案版。打印仍走 `renderBlocks` + KaTeX CSS。未改导出实现。
