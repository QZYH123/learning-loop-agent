from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
API_JS = (ROOT / "frontend/js/api.js").read_text(encoding="utf-8")


def test_generating_refresh_and_chat_poll_use_500ms():
    watch = APP_JS.split("watchGeneratingMessages() {", 1)[1].split("watchProcessingSources", 1)[0]
    assert "}, 500)" in watch
    assert "3000" not in watch
    assert "workspace === 'learn'" not in watch
    poll = APP_JS.split("async pollSessionMessageOperation", 1)[1].split("async ", 1)[0]
    assert "intervalMs: 500" in poll
    assert "maxIntervalMs: 500" in poll
    assert "intervalMs = 400" in API_JS or "intervalMs = 400" in API_JS.replace(" ", "")
    assert "maxIntervalMs = 2500" in API_JS
    assert "EventSource" not in APP_JS
    assert "WebSocket" not in APP_JS
    assert "EventSource" not in API_JS
    assert "WebSocket" not in API_JS
