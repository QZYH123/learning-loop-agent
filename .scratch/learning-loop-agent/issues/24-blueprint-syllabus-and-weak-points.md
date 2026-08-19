# 24 — 蓝图考点可见与错点回流

**What to build:** 让蓝图考纲（`syllabus`）在界面可见、可删，并真正约束题目生成；在此基础上，组新卷时把最近一次作答答错或遗漏的考点交给蓝图解析模型参考，用户在可见考纲里把关。不做错题本、复习日历、掌握度。

**Blocked by:** 23 — 题目说明与作答复盘（用户先能看懂错在哪，「再出一套」才有意义）

**Status:** ready-for-human

**Copy and layout source of truth:** `docs/frontend-workspaces.md`。

## 用户能看到什么

1. 蓝图页在组卷描述下方显示「考点」一行；草稿状态可以逐个删除，确认后只读。
2. 做过题之后在组卷对话里说「再出一套，重点考我错的地方」，新蓝图的考点里出现上次答错或遗漏的考点；不想要就删掉再确认。
3. 生成的题目围绕考点出，而不是只有检索沾边。
4. 没有作答记录时，组卷体验与现在完全相同。

## 现状（已对照代码核实，不要重做）

- `blueprint.syllabus` 已存在，解析时由模型从组卷要求里提取；`PATCH /api/exam-blueprints/{id}` 已支持改 `syllabus`（`ExamBlueprintPatch`），前端 `api.updateBlueprint` 也已封装，但没有任何 UI 调用
- `exam.js` 的 `renderBlueprint` 只显示 prompt、题型计划和总分，考纲对用户完全不可见
- `_generate_question`（`backend/app/exams.py`）只把 `syllabus` 拼进检索词；`general-knowledge` 模式不检索，考纲对生成零影响
- 错点数据齐全无出口：`attempt.feedback` 含 `correct` / `missed_points`，题目含 `knowledge_points`

## 设计

三件事按依赖顺序，一起交付：

### 1. 考纲约束生成（后端，一行）

`_generate_question` 的提示词加一行 `考纲重点：{顿号分隔的 syllabus，空则「无」}`。检索词用法保留。从此考纲在三种依据模式下都真实起作用，错点回流才有意义。

### 2. 考点可见、可删（前端）

`renderBlueprint` 的 draft / confirmed 视图，在 prompt 下方渲染考点行：

- 复用 `.cite` 一类的 chip 样式，顿号级别的短词排一行，可换行
- `status === 'draft'` 时每个 chip 带删除，调 `api.updateBlueprint(id, { syllabus })` 后刷新列表；confirmed 后只读
- 考纲为空时整行不渲染，不加新增/编辑输入框——要补考点，在组卷对话里说清楚重新解析（现有路径）
- 界面用词是「考点」，不出现 `syllabus`

### 3. 错点回流（后端，只改 parse_blueprint 的提示词组装）

- 取该科目最近一次带反馈的作答（按 `updated_at`），汇总 `correct === false` 或 `missed_points` 非空的题目的 `knowledge_points`，去重，上限 10 条
- 作为参考段附进蓝图解析提示词，注明：仅当用户表达复习、巩固、再出一套等意图时才纳入考纲，否则忽略
- 不写意图检测代码，判断交给模型；结果落在可见考纲里，由用户删改把关
- 没有符合条件的作答时，提示词与现在逐字节相同

## 不要做

- 不新增 HTTP 路径、契约字段或第二份错点存储
- 不自动确认蓝图、不自动开组题；错点只出现在待确认的考纲里
- 不做错题列表页、间隔复习、掌握度、下一课推荐
- 不改 `_chat_style_instruction`（原「阶段 3」所列行为已全部在现有指令中，无剩余需求）

## Contract

- [ ] 只用现有 `PATCH /api/exam-blueprints/{id}` 修改考纲
- [ ] 无作答记录时 `parse_blueprint` 的模型输入与现在完全相同

## Frontend

- [ ] 蓝图页显示考点行；draft 可逐个删除，confirmed 只读
- [ ] 删除后蓝图列表与详情同步刷新
- [ ] 界面只出现「考点」，无 `syllabus` / `knowledge_points` 等内部词

## Backend

- [ ] `_generate_question` 提示词包含考纲重点
- [ ] `parse_blueprint` 汇总最近作答错点（去重、上限 10）附进解析提示词
- [ ] 蓝图解析失败、确认、组题的现有测试保持通过

## Verification

- [ ] 测试：无作答记录时提示词不含错点段；有错题时含且去重、不超上限；PATCH `syllabus` 生效并触发校验
- [ ] 浏览器走通：
  1. 做一次练习并答错若干题 → 回组卷对话说「再出一套，重点考我错的地方」
  2. 新蓝图考点里出现错过的考点 → 删掉一个 → 确认蓝图 → 开始组题
  3. 生成的题目围绕保留的考点
  4. 新科目（无作答记录）组卷 → 考点行按解析结果正常显示，无错点内容

## Comments

- 2026-08-19：后端合入 `da77bce`，前端芯片合入 `adc6e95`。生成提示词含「考纲重点」；有错题时解析提示词附参考错点（去重、上限 10）；蓝图页 draft 可删考点、confirmed 只读。浏览器已走通删除芯片和组卷/作答说明块。未用真实模型走「再出一套」生成新题。
- 2026-08-19：已认领后端部分（考纲进生成提示词 + 错点进解析提示词），与 Issue 23 在隔离 worktree 并行。蓝图芯片 UI 和浏览器走通等 23 合入后再做。
- 本 Issue 取代 Issue 23 早期草稿里的「阶段 2」。原设计把错点直接写进 syllabus 草稿，但考纲当时既不可见也不约束生成，写进去等于静默丢弃；先修通路，再让模型在用户可见处提议，是更小也更诚实的闭环。
- 原「阶段 3」（加厚苏格拉底/章节速成指令）经核对已由现有 `LearningService._chat_style_instruction` 完整覆盖，不再立项；若实际对话行为不达预期，届时按具体案例另开。
