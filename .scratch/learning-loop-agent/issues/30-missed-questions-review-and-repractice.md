# 30 — 错题视图与「再练一套」

**Type:** task

**Status:** resolved

**Source:** 竞争力判断：错题回流是练习闭环与通用聊天工具拉开差距的核心一步。数据已齐（attempts、feedback、knowledge_points），Agent 的 `get_study_state` 也在读；缺一个极简呈现和一个回到组卷的入口。Issue 24/26 已要求「错点出现在新蓝图考点里且用户能认出来」。

## 范围

做：科目内跨试卷错题的只读投影接口、作答区错题 tab、「再练一套」到蓝图的入口。
不做：新存储或错题标记编辑、遗忘曲线/复习计划、跨科目聚合、Agent 新工具（`get_study_state` 已够用）。

## 设计规定

### 后端

- 新增契约与实现：`GET /api/subjects/{subject_id}/missed-questions`，operationId `listMissedQuestions`。**纯读投影，不建新存储。**
- 数据来源：该科目全部 attempts 的 feedback 中 `correct == False` 或 `missed_points` 非空的题；同一题（exam_id + question_id）多次答错只保留最近一次。泛化 `ExamService._recent_missed_knowledge_points` 的取数逻辑（它现在只看最近一次作答），抽出共享函数，两处复用，不复制粘贴。
- 返回按考点分组：`{items: [{knowledge_point, miss_count, questions: [{exam_id, exam_version_id, exam_title, question_id, question_type, stem_preview, attempt_id, missed_at}]}]}`。`stem_preview` 取题干纯文本前 80 字；考点最多 30 组、每组题最多 10 道，按 `missed_at` 倒序。**不回传**答案与反馈明细。
- 题目内容取自 `exam_version_id` 对应的固定版本（资料失效/试卷改版不重写历史，沿用现有版本读取路径）。

### 前端（作答区）

- 作答区右侧顶部加 tab：「试卷」（现状内容）/「错题」，交互模式照抄组卷区 `examTab`。空状态两行内：「还没有错题」+「去作答」。
- 错题列表按考点分组：组头 = 考点名 + 错题数；组内每行 = 题型 + 题干预览 + 来源试卷名 + 时间。点击行 → 打开对应作答复盘定位到该题（复用现有 attempt 复盘视图与 `openToolResource` 的 attempt 跳转路径）。
- 主操作「再练一套」：默认勾选错题数最多的前 5 个考点（复选可增减）→ 跳组卷区，调用现有 `parseBlueprint`，prompt 用固定模板：`针对以下薄弱考点出一套复习卷：{考点1}、{考点2}…`。考点进蓝图 syllabus 芯片，**可见可删**（蓝图考点芯片可删已实现，直接复用），兑现 Issue 26「错点回流不可见」的修复。
- 后续流程（确认蓝图 → 组题 → 发布）完全走现状，不加捷径。

## 验收标准

1. 做错客观题与被指出遗漏点的主观题都会出现在错题 tab，按考点分组、跨试卷聚合（行为测试造两份试卷各答错若干）。
2. 「再练一套」生成的蓝图 syllabus 含所选考点且可删；未选考点不出现。
3. 同一题重复答错不重复计数（保留最近一次）。
4. 接口不泄漏答案（考试模式进行中的 attempt 不参与投影——只统计有 feedback 的作答）。
5. 全量 pytest 通过。

## Comments

- 2026-08-20：按顺序开工。`_recent_missed_knowledge_points` 仍只看最近一次带反馈的作答。作答区尚无 tab。

## Answer

已落地。`GET /api/subjects/{id}/missed-questions` 按考点分组的只读投影；`_collect_missed_questions` 供列表和 `_recent_missed_knowledge_points` 共用。作答区「试卷 / 错题」tab，主操作「再练一套」用固定 prompt 走现有 `parseBlueprint`。行为测试覆盖跨卷聚合、去重、考试中作答不入投影、无答案泄漏。全量 pytest 131 passed。

偏离：「未标考点」只用于错题分组，不写进组卷参考错点。
