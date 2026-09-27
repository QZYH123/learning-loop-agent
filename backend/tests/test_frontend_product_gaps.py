from backend.tests.support.frontend import ROOT, load_js

APP_JS = load_js("app.js")
API_JS = load_js("api.js")
UTIL_JS = load_js("util.js")
EXAM_JS = load_js("components/exam.js")
SOURCES_JS = load_js("components/sources.js")
ATTEMPT_JS = load_js("components/attempt.js")
TIMER_JS = load_js("attempt-timer.js")
CHAT_JS = load_js("components/chat.js")
NAVBAR_JS = load_js("components/navbar.js")
MODAL_JS = load_js("components/modal.js")
MODELS_JS = load_js("components/models.js")
CSS = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
def test_blueprint_structure_is_editable():
    assert 'data-action="plan-type"' in EXAM_JS
    assert 'data-action="plan-difficulty"' in EXAM_JS
    assert 'data-action="add-plan-row"' in EXAM_JS
    assert 'data-action="remove-plan-row"' in EXAM_JS
    assert 'data-action="plan-duration"' in EXAM_JS
    assert "建议用时" in EXAM_JS
    assert "async addBlueprintPlanRow(" in APP_JS
    assert "async updateBlueprintDuration(" in APP_JS
    assert "duration_minutes" in APP_JS


def test_draft_hand_edit_reorder_and_delete_are_wired():
    assert "export function questionFromEditor(" in EXAM_JS
    assert 'data-action="toggle-question-edit"' in EXAM_JS
    assert 'data-action="save-question-edit"' in EXAM_JS
    assert 'data-action="move-question"' in EXAM_JS
    assert 'data-action="delete-question"' in EXAM_JS
    assert "replaceDraftQuestion(" in API_JS
    assert "deleteDraftQuestion(" in API_JS
    assert "updateDraft(" in API_JS
    assert "question_order" in APP_JS
    assert "async saveDraftQuestionEdit(" in APP_JS


def test_revision_preview_renders_question_structure():
    assert "function renderProposalDiff(" in EXAM_JS
    assert "function renderChangeSide(" in EXAM_JS
    assert "renderBlocks(value.stem)" in EXAM_JS
    assert "stringifyChange" not in EXAM_JS
    assert "无法预览这次修改" in EXAM_JS


def test_source_document_and_exam_versions_are_restorable():
    assert 'data-action="view-source-version"' in SOURCES_JS
    assert 'data-action="view-ai-doc-version"' in SOURCES_JS
    assert 'data-action="restore-ai-doc-version"' in SOURCES_JS
    assert "恢复此版" in SOURCES_JS
    assert "修改当前" in SOURCES_JS
    assert 'data-action="revise-ai-doc"' in SOURCES_JS
    assert 'data-action="delete-ai-doc"' in SOURCES_JS
    assert "deleteAiDocument(" in API_JS
    assert "restoreExamVersion(" in API_JS
    assert "restoreAiDocumentVersion(" in API_JS
    assert 'data-action="restore-exam-version"' in EXAM_JS
    assert "listExamVersions(" in APP_JS


def test_exam_countdown_and_suggested_score_are_separate():
    assert "export function examDurationMinutes(" in TIMER_JS
    assert "export function attemptRemainingMs(" in TIMER_JS
    assert "data-limit-ms" in ATTEMPT_JS
    assert "建议 ${minutes} 分钟" in ATTEMPT_JS
    assert "剩余时间" in ATTEMPT_JS
    assert "show_suggested_score: false" in APP_JS
    assert 'data-action="toggle-suggested-score"' in ATTEMPT_JS
    assert "updateAttempt(" in API_JS
    assert "async expireExamAttempt(" in APP_JS
    assert "时间到，已完成作答" in APP_JS
    assert "timedOut" in APP_JS


def test_menus_support_keyboard_and_accessible_names():
    assert "handleMenuKeys(" in APP_JS
    assert "ArrowDown" in APP_JS
    assert 'role="menu"' in CHAT_JS
    assert 'role="menuitem"' in CHAT_JS
    assert 'aria-label="对话风格"' in CHAT_JS
    assert 'aria-label="科目"' in NAVBAR_JS
    assert 'aria-label="${label}"' in NAVBAR_JS
    assert "aria-expanded" in MODELS_JS
    assert ".menu-item.is-focused" in CSS


def test_run_log_is_outside_learning_workspaces():
    assert "open-runs" in NAVBAR_JS
    assert "运行记录" in MODAL_JS
    assert "准备 " in MODAL_JS
    assert "生成 " in MODAL_JS
    assert "外层耗时" not in MODAL_JS
    assert "答案露出" in MODAL_JS
    assert "listOrchestrationRuns(" in API_JS
    assert "runEvaluationSuite(" in API_JS
    assert "编排运行" not in MODAL_JS
    assert "select-workspace" not in MODAL_JS.split("function runsDialog", 1)[1]


def test_print_keeps_questions_and_math_together():
    assert "page-break-inside: avoid" in CSS
    assert ".katex-display" in CSS.split("@media print", 1)[1]
    assert "katex.min.css" in APP_JS
    assert "break-inside: avoid" in CSS.split("@media print", 1)[1]


def test_plain_text_helpers_exist():
    assert "export function textToMarkdownBlocks(" in UTIL_JS
    assert "export function blocksArePlainText(" in UTIL_JS
    assert "export function nextOptionId(" in UTIL_JS
    assert "export const QUESTION_TYPE_ORDER" in UTIL_JS
