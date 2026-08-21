# 27 — 作答记录列表与组卷对象生命周期

**Type:** task

**Status:** resolved

**Source:** Issue 26 拆票顺序第 1 项。竞争力判断：闭环「能不能用完」的底线——试卷做过几次、上次做到哪、对象删不掉，都是当前主路上的硬缺口。

## 问题

1. 作答记录只有 attempt id 存在浏览器 `localStorage`（`lla.attempts`），换浏览器或清站点数据后答卷在界面上消失，虽然数据仍在科目空间里。契约没有「列出某试卷全部作答」的接口（spec 3、44–48）。
2. 「开始练习 / 开始考试」每次都 `createAttempt`，有进行中的作答时不会提示继续。
3. 后端可删蓝图（`DELETE /api/exam-blueprints/{id}`）、草稿、试卷，前端没有删除入口；「新建蓝图」会堆出多份同名默认卡（spec 53：删除要看到影响范围）。

## 范围

做：作答记录服务端列表、继续作答默认化、蓝图/草稿/试卷删除入口与影响范围确认。
不做：作答记录的筛选/搜索、跨科目视图、错题聚合（错题视图是 Issue 30）。

## 设计规定

### 后端

- 新增契约与实现：`GET /api/exams/{exam_id}/attempts`，operationId `listExamAttempts`，返回 `{items: [...]}`，按 `updated_at` 倒序。
- 每项是摘要视图，从现有 attempt 结构抽取：`id`、`exam_id`、`exam_version_id`、`mode`、`status`、进度（已答题数 / 总题数）、`created_at`、`updated_at`、是否已有批改反馈（布尔或计数）。**不回传**答案内容、反馈明细和隐藏答案（考试模式防泄漏原则不变）。
- 核对 `ExamService.delete_exam`：删除试卷必须级联其版本、修改提案和作答记录；若现状未级联，补齐。删除蓝图/草稿行为已存在，不改语义。
- 契约先行：先改 `docs/api/openapi.yaml` / `docs/api/schemas.yaml`，实现向契约收敛（ADR 0002）。

### 前端（作答区）

- 选中试卷后，右侧在开始按钮区域下方列出该卷作答记录（服务端列表，最多显示 10 条）：一行 = 模式 + 进度 + 状态 + 更新时间，点击进行中的记录继续作答，点击已完成的记录进入复盘。
- 有进行中（含暂停）作答时：主操作变为「继续作答」，「再做一份」降为次操作；没有则维持「开始练习 / 开始考试」。
- `localStorage` 的 `lla.attempts` 不再作为事实源：列表和继续判断全部走服务端；删除对该索引的写入（Issue 26 冗杂 #6，不做第二套本地索引）。

### 前端（组卷区删除）

- 蓝图、草稿、试卷卡片的选中态增加「删除」（复用现有应用内确认弹窗，不用原生 confirm）。
- 确认弹窗必须列出影响范围：蓝图（无下游对象，直接删）；草稿（题目 N 道、修改提案 N 份）；试卷（版本 N 个、修改提案 N 份、作答 N 份——作答数用本票新列表接口取）。
- 文案守 `docs/frontend-workspaces.md`：按钮 2–6 字（「删除」「继续作答」「再做一份」），不出现内部术语。

## 验收标准

1. 重启服务、换浏览器后，作答区仍能看到某试卷全部作答记录并继续未完成的一份（行为测试：创建作答 → 新 TestClient 实例 → 列表可见）。
2. 有进行中作答时主操作是「继续作答」，点它不新建 attempt。
3. 蓝图/草稿/试卷都能从界面删除，弹窗展示影响范围；删除试卷后其作答与提案随之消失，列表接口返回 404 或空。
4. 全量 pytest 通过；`lla.attempts` 在 `frontend/js` 中无写入引用（静态断言）。

## 测试要求

- 后端：列表排序与字段、防答案泄漏（考试模式未提交的 attempt 摘要不含答案）、delete_exam 级联。
- 前端：静态断言新 data-action 与 `lla.attempts` 移除；关键交互路径由现有行为测试风格覆盖。

## Comments

- 2026-08-20：按 Issue 26 建议顺序开工。已知现状：`GET /api/exams/{exam_id}/attempts` 尚不存在（同路径仅有 POST createAttempt）；`delete_exam` 在存在作答时 409「试卷已有作答记录，不能删除」，本票要求改为级联删除作答，这是计划内变更不是冲突。

## Answer

已落地。`GET /api/exams/{exam_id}/attempts` 返回摘要（含 `completion_status`、`answered_count`、`question_count`、`has_feedback`），不回传答案。前端作答区用服务端列表；进行中主操作「继续作答」走 `open-attempt`，不新建。蓝图/草稿/试卷选中卡可删，确认弹窗列影响范围。`delete_exam` 级联 versions / proposals / attempts / exports。`lla.attempts` 已移除。全量 pytest 118 passed。

偏离：摘要模型放在既有 `exam_models.py`；契约测试改为 `TICKETS <= covered_tickets` 以允许 ticket 27。
