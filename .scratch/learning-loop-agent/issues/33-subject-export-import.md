# 33 — 科目空间导出与导入

**Type:** task

**Status:** resolved

**Source:** 竞争力判断：本地优先承诺的兑现——「数据属于用户」需要一个可带走、可恢复的形式。现状数据分散在 `data/workspace.json`（科目节点）与资料原文件/解析索引/引用记录之间，用户无法安全备份单个科目。

## 范围

做：单科目导出 zip、导入 zip 恢复为科目。
不做：双向同步、增量备份、跨版本迁移工具、云端存储（Out of Scope 已定）。导出是明确副本（spec 13）。

## 设计规定

### 导出

- 新增契约与实现：`GET /api/subjects/{subject_id}/export`，operationId `exportSubject`，返回 `application/zip`，`Content-Disposition` 文件名 `{科目名}-{日期}.zip`。
- zip 内容：
  - `manifest.json`：`schema_version: 1`、导出时间、科目 id/名称、文件清单；
  - `subject.json`：workspace 中该科目节点完整 JSON（资料、版本、会话、蓝图、草稿、试卷、版本、作答、AI 文档、学习产物）；
  - `sources/`：该科目全部资料版本的原文件与解析缓存（按 `SourceLibrary` 的 cache/index 布局收集：原文件、`{version_id}.json` 索引、assets 目录）；
  - `citations.json`：全局引用记录中属于该科目资料版本的条目。
- 同步导出（科目数据量本地可控），不走 operation；若后续过慢再议。

### 导入

- 新增：`POST /api/subjects/import`（multipart 上传 zip），operationId `importSubject`。
- 冲突策略（定死，不给设计空间）：**保留原 id**。若工作区已存在相同 subject id 或任一 source version id，整体拒绝（409，提示「该科目已存在，请先删除或重命名现有科目」），不做 id 重映射、不做合并。科目名与现有重名但 id 不同时，导入名自动加「（导入）」后缀。
- 校验 `manifest.schema_version`，不认识的版本 422 明确提示。文件落回 cache/index/citations 对应位置后，资料状态按原样恢复（ready 的仍 ready，不重新解析）。

### 前端

- 科目菜单（现有重命名/删除所在处）加两项：「导出」（直接下载）、「导入」（文件选择器，成功后切到新科目并 toast「已导入」）。按钮 2–6 字，失败 toast 用服务端 message。

## 验收标准

1. 导出的 zip 在**空数据目录的新实例**导入后：资料可检索、旧会话与引用可查、试卷可作答、历史作答可复盘（行为测试覆盖导出 → 清库 → 导入 → 逐项断言）。
2. 重复导入同一 zip 被 409 拒绝且提示明确。
3. 损坏 zip / 缺 manifest 得到 422 中文提示，不产生半导入状态（先全量校验再落盘）。
4. 全量 pytest 通过。

## Comments

- 2026-08-20：最后一张票开工。资料文件在 `source-files/{version_id}.bin`，索引 `source-index/{version_id}.json`，缓存 `source-cache/{hash}.json` 与 `{hash}.assets/`。引用在全局 `citations.json`。

## Answer

已落地。`GET /api/subjects/{id}/export` 打 zip（manifest + subject.json + sources/ + 该科 citations）；`POST /api/subjects/import` 保留原 id，冲突 409，坏包 422 且不半导入。科目菜单有导出/导入。空库导入后资料可检索、会话/引用/试卷/作答可恢复。全量 pytest 161 passed。
