from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_JS = ROOT / "frontend/js"
APP_JS = (FRONTEND_JS / "app.js").read_text(encoding="utf-8")
API_JS = (FRONTEND_JS / "api.js").read_text(encoding="utf-8")
EXAM_JS = (FRONTEND_JS / "components/exam.js").read_text(encoding="utf-8")
MODAL_JS = (FRONTEND_JS / "components/modal.js").read_text(encoding="utf-8")


def test_exam_export_api_wrappers_exist():
    assert "getExamRenderDocument(" in API_JS
    assert "createExamExport(" in API_JS
    assert "getExamExport(" in API_JS
    assert "downloadExamExport(" in API_JS
    assert "/render-document" in API_JS
    assert "/exports" in API_JS
    assert "createObjectURL" in API_JS
    assert "window.open" not in API_JS


def test_exam_more_menu_entries():
    assert 'data-menu="exam-more"' in EXAM_JS
    assert "打印" in EXAM_JS
    assert "导出 PDF" in EXAM_JS
    assert "导出 Markdown" in EXAM_JS
    assert "print-exam" in EXAM_JS
    assert "export-exam-pdf" in EXAM_JS
    assert "export-exam-markdown" in EXAM_JS
    assert "moreHorizontal" in EXAM_JS
    assert 'data-action="go-attempt"' in EXAM_JS


def test_edition_modal_defaults_to_questions():
    assert "modal === 'exam-edition'" in MODAL_JS
    assert "题目版" in MODAL_JS
    assert "答案版" in MODAL_JS
    assert "答案版包含答案与解析" in MODAL_JS
    assert 'value="questions"' in MODAL_JS
    assert 'value="solutions"' in MODAL_JS
    assert "examEdition === 'solutions' ? 'solutions' : 'questions'" in MODAL_JS
    assert "examEdition: 'questions'" in APP_JS
    assert "this.askExamEdition(" in APP_JS


def test_print_reuses_existing_question_renderers():
    assert "from './solution.js'" in EXAM_JS
    assert "renderSolution" in EXAM_JS
    assert "export function renderExamQuestion(" in EXAM_JS
    assert "export function renderExamPrintDocument(" in EXAM_JS
    assert "renderExamQuestion(merged" in EXAM_JS
    assert "renderExamPrintDocument" in APP_JS
    assert "function printQuestionHtml" not in EXAM_JS
    assert "function printQuestionHtml" not in APP_JS
    print_fn = APP_JS.split("async printExam(", 1)[1].split("async ", 1)[0]
    assert "renderExamPrintDocument" in print_fn
    assert "<article class=\"q\"" not in print_fn


def test_edition_request_uses_contract_enums_only():
    joined = "\n".join([APP_JS, API_JS, EXAM_JS, MODAL_JS])
    assert "questions-only" not in joined
    assert "'answer'" not in APP_JS.split("async confirmExamEdition(", 1)[1].split("async ", 1)[0]
    confirm_fn = APP_JS.split("async confirmExamEdition(", 1)[1].split("async ", 1)[0]
    assert "solutions" in confirm_fn
    assert "questions" in confirm_fn
    export_fn = APP_JS.split("async exportExam(", 1)[1].split("async ", 1)[0]
    assert "createExamExport" in export_fn
    assert "pollOperation" in export_fn
    assert "downloadExamExport" in export_fn
    assert "trackOperation" in export_fn
    assert "正在导出" in APP_JS
