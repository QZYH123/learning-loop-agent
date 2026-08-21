from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_JS = ROOT / "frontend/js"
APP_JS = (FRONTEND_JS / "app.js").read_text(encoding="utf-8")
API_JS = (FRONTEND_JS / "api.js").read_text(encoding="utf-8")
STORE_JS = (FRONTEND_JS / "store.js").read_text(encoding="utf-8")
ATTEMPT_JS = (FRONTEND_JS / "components/attempt.js").read_text(encoding="utf-8")


def test_attempt_missed_tab_and_practice_entry():
    assert 'data-action="attempt-tab"' in ATTEMPT_JS
    assert 'data-tab="exams"' in ATTEMPT_JS
    assert 'data-tab="missed"' in ATTEMPT_JS
    assert ">试卷<" in ATTEMPT_JS
    assert ">错题<" in ATTEMPT_JS
    assert "再练一套" in ATTEMPT_JS
    assert "还没有错题" in ATTEMPT_JS
    assert "去作答" in ATTEMPT_JS
    assert 'data-action="open-missed-question"' in ATTEMPT_JS
    assert "data-attempt-id=" in ATTEMPT_JS
    assert "data-question-id=" in ATTEMPT_JS
    assert 'data-action="practice-missed-set"' in ATTEMPT_JS
    assert 'data-action="toggle-missed-point"' in ATTEMPT_JS
    assert "attemptTab: 'exams'" in STORE_JS
    assert "listMissedQuestions(" in API_JS
    assert "/api/subjects/" in API_JS and "missed-questions" in API_JS
    assert "async loadMissedQuestions(" in APP_JS
    assert "async openMissedQuestion(" in APP_JS
    assert "async practiceMissedSet(" in APP_JS
    assert "针对以下薄弱考点出一套复习卷：" in APP_JS
    assert "请先选择考点" in APP_JS
    assert "action === 'attempt-tab'" in APP_JS
    assert "action === 'open-missed-question'" in APP_JS
    assert "action === 'practice-missed-set'" in APP_JS
    open_fn = APP_JS.split("async openMissedQuestion(", 1)[1].split("async ", 1)[0]
    assert "this.openAttempt(" in open_fn
    assert "data-question-id" in open_fn
    assert "scrollIntoView" in open_fn
    practice_fn = APP_JS.split("async practiceMissedSet(", 1)[1].split("async ", 1)[0]
    assert "请先选择考点" in practice_fn
    assert "parseBlueprint(" in practice_fn
    assert "workspace: 'exam'" in practice_fn
