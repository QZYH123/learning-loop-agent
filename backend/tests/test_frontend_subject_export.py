from backend.tests.support.frontend import load_js

APP_JS = load_js("app.js")
API_JS = load_js("api.js")
NAVBAR_JS = load_js("components/navbar.js")


def test_subject_menu_has_export_and_import_actions():
    assert "导出" in NAVBAR_JS
    assert "导入" in NAVBAR_JS
    assert 'data-action="export-subject"' in NAVBAR_JS
    assert 'data-action="import-subject"' in NAVBAR_JS
    assert 'accept=".zip"' in NAVBAR_JS
    assert "export-subject" in NAVBAR_JS
    assert "import-subject" in NAVBAR_JS


def test_subject_export_import_api_wrappers_exist():
    assert "exportSubject(" in API_JS
    assert "importSubject(" in API_JS
    assert "/export" in API_JS
    assert "/api/subjects/import" in API_JS
    assert "createObjectURL" in API_JS
    assert "FormData" in API_JS


def test_import_switches_subject_and_toasts_success():
    assert "async exportSubject(" in APP_JS
    assert "async importSubject(" in APP_JS
    import_fn = APP_JS.split("async importSubject(", 1)[1].split("async ", 1)[0]
    assert "已导入" in import_fn
    assert "switchSubject" in import_fn
    assert "err.message" in import_fn
