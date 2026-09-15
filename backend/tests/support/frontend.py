from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_JS = ROOT / "frontend/js"


def load_js(relpath) -> str:
    return (FRONTEND_JS / relpath).read_text(encoding="utf-8")
