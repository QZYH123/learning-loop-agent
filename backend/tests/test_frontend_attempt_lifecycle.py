from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_JS = ROOT / "frontend/js"
APP_JS = (FRONTEND_JS / "app.js").read_text(encoding="utf-8")
API_JS = (FRONTEND_JS / "api.js").read_text(encoding="utf-8")
STORE_JS = (FRONTEND_JS / "store.js").read_text(encoding="utf-8")
ATTEMPT_JS = (FRONTEND_JS / "components/attempt.js").read_text(encoding="utf-8")
EXAM_JS = (FRONTEND_JS / "components/exam.js").read_text(encoding="utf-8")


def _frontend_js_sources():
    return [path.read_text(encoding="utf-8") for path in FRONTEND_JS.rglob("*.js")]


def test_attempt_list_and_continue_actions_are_wired():
    assert 'data-action="open-attempt"' in ATTEMPT_JS
    assert 'data-action="start-another"' in ATTEMPT_JS
    assert "继续作答" in ATTEMPT_JS
    assert "再做一份" in ATTEMPT_JS
    assert "action === 'open-attempt'" in APP_JS
    assert "this.openAttempt(id)" in APP_JS
    assert "action === 'start-another'" in APP_JS
    assert "api.createAttempt" in APP_JS
    assert "async startAttempt(" in APP_JS
    assert "async openAttempt(" in APP_JS
    start_fn = APP_JS.split("async startAttempt(", 1)[1].split("async ", 1)[0]
    open_fn = APP_JS.split("async openAttempt(", 1)[1].split("async ", 1)[0]
    assert "createAttempt" in start_fn
    assert "createAttempt" not in open_fn
    assert "continueAttempt" not in open_fn
    assert "listExamAttempts" in API_JS
    assert "this.loadExamAttempts" in APP_JS


def test_exam_object_delete_actions_use_in_app_confirm():
    assert 'data-action="delete-blueprint"' in EXAM_JS or "deleteAction: 'delete-blueprint'" in EXAM_JS
    assert "deleteAction: 'delete-draft'" in EXAM_JS
    assert "deleteAction: 'delete-exam'" in EXAM_JS
    assert "action === 'delete-blueprint'" in APP_JS
    assert "action === 'delete-draft'" in APP_JS
    assert "action === 'delete-exam'" in APP_JS
    assert "this.askConfirm(" in APP_JS
    assert "action: 'delete-blueprint'" in APP_JS
    assert "action: 'delete-draft'" in APP_JS
    assert "action: 'delete-exam'" in APP_JS
    assert "deleteDraft(" in API_JS
    assert "deleteExam(" in API_JS
    assert "window.confirm" not in APP_JS
    assert "题目 " in APP_JS
    assert "修改提案 " in APP_JS
    assert "作答 " in APP_JS


def test_local_attempt_index_removed():
    sources = _frontend_js_sources()
    joined = "\n".join(sources)
    assert "lla.attempts" not in joined
    assert "rememberAttempt" not in joined
    assert "attemptsByExam" not in joined
    assert "ATTEMPTS_KEY" not in STORE_JS
    assert "writeJson(ATTEMPTS_KEY" not in STORE_JS
