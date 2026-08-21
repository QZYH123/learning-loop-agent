from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_JS = ROOT / "frontend/js"
APP_JS = (FRONTEND_JS / "app.js").read_text(encoding="utf-8")
API_JS = (FRONTEND_JS / "api.js").read_text(encoding="utf-8")
CHAT_JS = (FRONTEND_JS / "components/chat.js").read_text(encoding="utf-8")
SOLUTION_JS = (FRONTEND_JS / "components/solution.js").read_text(encoding="utf-8")
SOURCES_JS = (FRONTEND_JS / "components/sources.js").read_text(encoding="utf-8")
STYLES = (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_citation_chips_are_buttons_with_jump_data():
    for source in (CHAT_JS, SOLUTION_JS):
        assert 'data-action="open-citation"' in source
        assert "data-source-id=" in source
        assert "data-version-id=" in source
        assert "data-anchor-id=" in source
        assert 'class="cite"' in source
        assert "<button type=\"button\" class=\"cite\"" in source
    assert 'id="anchor-${anchor.id}"' in SOURCES_JS or 'id="anchor-' in SOURCES_JS


def test_open_citation_handles_unavailable_source():
    assert "async openCitation(" in APP_JS
    assert "this.openCitation(" in APP_JS
    assert "getCitation(" in API_JS
    assert "/api/citations/" in API_JS
    assert "资料已不可用" in APP_JS
    assert "SOURCE_UNAVAILABLE" in APP_JS
    assert "err.status === 410" in APP_JS
    assert "highlightCitedAnchor" in APP_JS
    assert "is-cited" in APP_JS
    assert "is-cited" in STYLES
    assert "--blue-soft" in STYLES
    assert "transition: background 0.18s ease" in STYLES
    assert "2000" in APP_JS
    open_fn = APP_JS.split("async openCitation(", 1)[1].split("async ", 1)[0]
    assert "workspace: 'sources'" in open_fn
    assert "sourceKind: 'files'" in open_fn
    assert "sourceKind: 'docs'" in open_fn
    assert "loadSourceDetail(sourceId, versionId" in APP_JS
    assert "{ required: true }" in open_fn
    assert "listSourceVersionAnchors" in API_JS
    load_idx = open_fn.find("loadSourceDetail(sourceId, versionId")
    files_idx = open_fn.find("sourceKind: 'files'")
    assert load_idx != -1 and files_idx != -1 and load_idx < files_idx
