# 23 — 题目说明与作答复盘

**What to build:** 把后端已经生成的解析、考点、出处和批改结果展示出来。组卷时用来验题，作答后用来看懂错在哪。不新增工作区、不新增接口、不改对话风格状态机。

**Blocked by:** 10 — 客观题答题；11 — 主观题批改反馈；21 — 作答完成与批改解耦（接口与作答纸已存在，本 Issue 收口它们的界面缺口）

**Status:** ready-for-human

**Copy and layout source of truth:** `docs/frontend-workspaces.md`。ADR-0004 仍然有效：不引入提示层级、复述关卡或复习日程。

## 用户能看到什么

1. 组卷草稿和已发布试卷：每道题在答案下方看到解析、考点、出处；依据不足标「待核查」。
2. 练习模式：客观题保存答案即看到对错 + 正确答案 + 解析；主观题点「本题反馈」后看到写到了什么、漏了什么。
3. 考试模式：点「完成作答」前，作答纸上不出现任何答案、解析或出处；完成后全卷揭晓解析，「提交批改」后再出对错和得分点。
4. 客观题答错不再只有一句「对照解析检查答案」，正确答案和解析直接可见。

## 现状（已对照代码核实，不要重做）

- 题目对象含 `answer`、`explanation`、`knowledge_points`、`evidence`（`basis` / `citations` / `status`），citation 含 `source_name` 和 `location.label`
- 作答纸 `AttemptPaper` 故意不含答案和解析；`GET /api/attempts/{id}/review` 是作答后解析的唯一来源：考试未完成返回 409；练习未完成只返回有反馈的题
- 练习模式保存客观题答案时，后端自动写入对错反馈到 `attempt.feedback`
- `store.state.review` 已存在，但只有 `gradeAttempt` 会写入；`attempt.js` 完全没用它
- `attempt.js` 的 `renderFeedback` 只画对错、建议分、suggestions、参考答案
- `exam.js` 草稿/试卷只画题干、选项、答案行（`.answer-key`），不画解析、考点、出处
- `_objective_feedback`（`backend/app/exams.py`）答错时 `suggestions = ["对照解析检查答案"]`

## 设计

### 数据来源，一条分工

- **作答结果**（对错、得分点、建议）读 `attempt.feedback` —— 它本来就随 attempt 返回，考试未完成时前端已有 `hideFeedback` 遮蔽。
- **题目说明**（答案、解析、考点、出处）读 `state.review` —— 只有它带完整题目。

不要从 review 里再取一份 feedback，也不要把解析塞进 `QuestionFeedback`。

### review 拉取，一条规则

可看 review ⇔ `mode === 'practice' || completion_status === 'completed'`。

在 `app.js` 加一个统一刷新入口（如 `refreshAttempt(id)`）：拉 attempt；若满足上述条件则并行拉 review，失败或 409 时 `review = null`，不当致命错误。`saveAnswer`、`askFeedback`、`completeAttempt`、`gradeAttempt`、`continueAttempt`、`restoreAttempt` 全部走它，删掉各处手写的 `review: null`。这条规则天然保证考试未完成不请求 `/review`。

### 共用说明块 `frontend/js/components/solution.js`

组卷和作答都引用，不在 `exam.js` / `attempt.js` 里各写一份。两个函数，可单独使用：

1. `renderSolution(question)` — 题目说明：
   - 解析（`explanation`）
   - 考点（`knowledge_points`，顿号分隔）
   - 出处（每条 citation 显示 `source_name` + `location.label`）；无引用且 `evidence.basis` 为常识/补充时显示对应标签
   - `evidence.status` 或 `reliability` 为 `needs-review` 时标「待核查」
2. `renderReview(feedback, options)` — 作答结果，替换现有 `renderFeedback`：
   - 正确 / 不正确 / 无法判断 / 待核查
   - 主观题：已写到、漏了、思路、建议、参考答案
   - 建议分仅 `show_suggested_score` 开启时显示
   - 客观题不编造得分点区块

样式复用并扩展 `.feedback`、`.answer-key`、`.cite`。说明块是题目正文的延续，不套大卡片；桌面和窄屏都不遮挡题干、选项和底部操作。

### 组卷工作区（`exam.js`）

草稿题和已发布试卷题，在现有答案行下调用 `renderSolution(slot.question / q)`：

- 草稿：`slot.question` 存在才渲染；生成中/失败不显示空说明；`needs-review` 沿用现有状态色
- 已发布试卷：作者视图，始终可见（这不是作答纸）
- 修改提案预览仍走现有 diff，不把说明塞进 diff 文本

### 作答工作区（`attempt.js`）

按 review 里的题目建索引（question_id → question）。每题渲染：

- 有 review 题目 → 在作答区下方 `renderSolution`
- 有 feedback 且非 `hideFeedback` → `renderReview`

review 为 null（考试未完成）时自然什么都不渲染，不需要额外的模式判断表。效果：

- 练习：客观题保存后立即出现对错 + 说明；主观题反馈后出现
- 考试：完成前只有题干和作答区；完成后全卷说明可见，批改后对错和得分点可见

「本题反馈」按钮只保留给主观题——客观题保存即出反馈，再点一次没有意义。左侧「问 AI」的考试防泄漏门禁（Issue 12 / 21）不要改松。

### 客观题反馈（后端，一处）

`_objective_feedback` 的 `suggestions` 恒为 `[]`（对错都是）。错题的正确答案和解析由界面从 review 渲染，契约不变。

## 文案

| 内部字段 | 界面用词 |
| --- | --- |
| `explanation` | 解析 |
| `knowledge_points` | 考点 |
| citation（`source_name` + `location.label`） | 出处 |
| `evidence.basis = general-knowledge` | 常识 |
| `evidence.basis = supplemental` | 补充 |
| `needs-review`（evidence / reliability / feedback） | 待核查 |
| `feedback.status = unable-to-assess` | 无法判断 |
| `correct` | 正确 / 不正确 |
| `matched_points` / `missed_points` | 已写到 / 漏了 |
| `reasoning_issues` / `suggestions` | 思路 / 建议 |
| `reference_answer` | 参考答案 |
| `suggested_score` | 建议分 |

按钮沿用现有：`本题反馈`、`完成作答`、`提交批改`、`继续作答`。不加教程句，不出现「解析锚点」「knowledge_points」等内部词。

## 不要做

- 不新增 HTTP 路径或 `QuestionFeedback` 字段
- 不做错题本、复习日历、掌握度、下一课推荐
- 不引入第二份 review 缓存；只用 `store.state.review`
- 不把 10 / 11 / 21 整张重写；本 Issue 只补它们未露出的说明

## Contract

- [ ] `GET /api/attempts/{attempt_id}/review` 仍是作答后解析/考点/出处的唯一来源，门禁不放宽
- [ ] 考试 `completion_status !== completed` 时不请求 review，作答纸不含答案和解析
- [ ] 客观题反馈不再返回「对照解析检查答案」

## Frontend

- [ ] 新增 `solution.js`：`renderSolution` / `renderReview`，组卷与作答复用
- [ ] 草稿和已发布试卷显示解析、考点、出处、待核查
- [ ] `app.js` 统一刷新入口按单条规则拉取/清空 review；`attempt.js` 读取并渲染
- [ ] 「本题反馈」仅主观题显示；建议分仅开启时出现
- [ ] 文案只用上表中的词；空状态和按钮遵守 `docs/frontend-workspaces.md`

## Backend

- [ ] `_objective_feedback` 的 `suggestions` 恒为空列表
- [ ] 对错判断、填空同义、考试门禁的现有测试保持通过

## Verification

- [ ] 新增/更新测试：客观题反馈 `suggestions` 为空；练习保存客观题后 review 含该题解析；考试未完成 review 仍 409
- [ ] 浏览器走通：
  1. 组一卷（含选择和简答）→ 草稿能看见解析/考点/出处；发布后试卷页同样可见
  2. 开始练习 → 做错选择题 → 不点任何按钮即看到不正确 + 正确答案 + 解析
  3. 简答点「本题反馈」→ 看到已写到/漏了，不是只有一句话
  4. 另开考试模式 → 做题过程中看不到解析；完成作答后全卷说明出现；提交批改后对错和建议分出现
  5. 桌面和窄屏下说明块不遮挡题干和主操作
- [ ] 页面无「解析锚点」、JSON、阶段条或新的一级导航

## Comments

- 2026-08-19：已合入 `main`（`a4e5d9c`）。`refreshAttempt` 按练习/已完成拉 review；组卷和作答共用 `solution.js`；客观题 `suggestions` 恒为空。浏览器已走通练习错选即出解析、考试完成前无解析、完成后揭晓。
- 2026-08-19：已认领。与 Issue 24 后端在隔离 worktree 并行；本 Issue 不做蓝图考纲和错点回流。
- 数据早已在后端和 review 接口里，本 Issue 只是把同一套说明块接到组卷和作答两处，是当前最高 ROI 的界面收口。
- Issue 10 / 11 注释里「前端尚未接入」已过时；本 Issue 完成后那两张的用户可见验收项即可勾。
- 后续排期：错点回流下次组卷已立项为 Issue 24（蓝图考点可见与错点回流），被本 Issue 阻塞；原「加厚对话风格指令」经核对已由现有 `_chat_style_instruction` 覆盖，不立项。
