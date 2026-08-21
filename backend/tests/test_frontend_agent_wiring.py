from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
CHAT_JS = (ROOT / "frontend/js/components/chat.js").read_text(encoding="utf-8")
API_JS = (ROOT / "frontend/js/api.js").read_text(encoding="utf-8")


def test_send_message_includes_workspace_context():
    assert "payload.workspace_context = this.currentWorkspaceContext()" in APP_JS
    assert "workspace:" in APP_JS
    assert "blueprint_id" in APP_JS
    assert "draft_id" in APP_JS
    assert "exam_id" in APP_JS
    assert "ai_document_id" in APP_JS
    assert "attempt_id" in APP_JS
    assert "createSessionMessage" in API_JS


def test_implicit_exam_parse_hack_removed():
    assert "content.length > 4" not in APP_JS
    assert "parseBlueprint(content)" not in APP_JS
    assert "async parseBlueprint(" in APP_JS
    assert "createDefaultBlueprint" in APP_JS
    assert "run: 'parseBlueprint'" in (ROOT / "frontend/js/commands.js").read_text(encoding="utf-8")


def test_tool_events_render_and_jump_wiring():
    assert "tool-event" in CHAT_JS
    assert "tool-event-card" in CHAT_JS
    assert 'data-action="open-tool-resource"' in CHAT_JS
    assert "open-tool-resource" in APP_JS
    assert "openToolResource" in APP_JS
    assert "selectBlueprint" in APP_JS
    assert "selectAiDoc" in APP_JS
    assert "refreshAfterToolEvents" in APP_JS
