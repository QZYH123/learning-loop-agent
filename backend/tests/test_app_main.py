import importlib
import io
import socket
from pathlib import Path

import pytest

from backend.app.__main__ import (
    DEFAULT_PORT,
    MISSING_DEPENDENCY_MESSAGE,
    PORTS_BUSY_MESSAGE,
    check_dependencies,
    find_available_port,
    main,
    parse_args,
    serve_url,
)
from backend.app.desktop import DESKTOP_MISSING_MESSAGE

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_find_available_port_skips_occupied():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert find_available_port("127.0.0.1", start=port, end=port) is None
    finally:
        sock.close()
    assert find_available_port("127.0.0.1", start=port, end=port) == port


def test_find_available_port_uses_next_free():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        found = find_available_port("127.0.0.1", start=port, end=port + 5)
        assert found is not None
        assert found != port
        assert port < found <= port + 5
    finally:
        sock.close()


def test_main_prints_fallback_address_when_default_port_busy():
    stdout = io.StringIO()
    code = main(
        ["--no-browser"],
        find_port=lambda: 4174,
        run_uvicorn=lambda **kwargs: None,
        stdout=stdout,
    )
    assert code == 0
    text = stdout.getvalue()
    assert "4173" in text
    assert "http://127.0.0.1:4174" in text
    assert "已被占用" in text
    assert "应用地址：http://127.0.0.1:4174" in text


def test_main_exits_when_all_ports_busy():
    stdout = io.StringIO()
    code = main(
        ["--no-browser"],
        find_port=lambda: None,
        run_uvicorn=lambda **kwargs: None,
        stdout=stdout,
    )
    assert code == 1
    assert PORTS_BUSY_MESSAGE in stdout.getvalue()


def test_unhandled_error_stays_a_short_message(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    app = create_app(data_dir=tmp_path)

    def boom(_subject_id):
        raise RuntimeError("secret traceback token")

    app.state.source_library.list_sources = boom
    client = TestClient(app, raise_server_exceptions=False)
    with client:
        missing = client.get("/api/subjects/missing-subject")
        assert missing.status_code == 404
        assert missing.json()["error"]["message"] != "这次没有完成，请再试一次"
        failed = client.get("/api/subjects/missing-subject/sources")
    assert failed.status_code == 500
    body = failed.json()["error"]
    assert body["code"] == "INTERNAL_ERROR"
    assert body["message"] == "这次没有完成，请再试一次"
    assert "secret" not in failed.text


def test_missing_dependency_message_has_no_traceback():
    stdout = io.StringIO()

    def boom(name):
        raise ImportError(name)

    code = main([], importer=boom, run_uvicorn=lambda **kwargs: None, stdout=stdout)
    assert code == 1
    text = stdout.getvalue()
    assert MISSING_DEPENDENCY_MESSAGE in text
    assert "Traceback" not in text
    assert check_dependencies(importer=boom) == MISSING_DEPENDENCY_MESSAGE


def test_no_browser_does_not_open():
    opened = []
    code = main(
        ["--no-browser"],
        find_port=lambda: DEFAULT_PORT,
        run_uvicorn=lambda **kwargs: None,
        open_browser=opened.append,
        stdout=io.StringIO(),
    )
    assert code == 0
    assert opened == []


def test_opens_browser_without_flag():
    opened = []
    code = main(
        [],
        find_port=lambda: DEFAULT_PORT,
        run_uvicorn=lambda **kwargs: None,
        open_browser=opened.append,
        stdout=io.StringIO(),
    )
    assert code == 0
    assert opened == [serve_url("127.0.0.1", DEFAULT_PORT)]


def test_parse_args_no_browser():
    assert parse_args(["--no-browser"]).no_browser is True
    assert parse_args([]).no_browser is False
    assert parse_args([]).desktop is False
    assert parse_args([]).browser is False


def test_parse_args_desktop_and_browser():
    assert parse_args(["--desktop"]).desktop is True
    assert parse_args(["--browser"]).browser is True
    with pytest.raises(SystemExit):
        parse_args(["--desktop", "--browser"])
    with pytest.raises(SystemExit):
        parse_args(["--desktop", "--no-browser"])


def test_desktop_opens_window_not_browser():
    opened_desktop = []
    opened_browser = []
    code = main(
        ["--desktop"],
        find_port=lambda: DEFAULT_PORT,
        run_uvicorn=lambda **kwargs: None,
        open_browser=opened_browser.append,
        open_desktop=opened_desktop.append,
        stdout=io.StringIO(),
    )
    assert code == 0
    assert opened_desktop == [serve_url("127.0.0.1", DEFAULT_PORT)]
    assert opened_browser == []


def test_frozen_defaults_to_desktop():
    opened_desktop = []
    opened_browser = []
    code = main(
        [],
        find_port=lambda: DEFAULT_PORT,
        run_uvicorn=lambda **kwargs: None,
        open_browser=opened_browser.append,
        open_desktop=opened_desktop.append,
        is_frozen_app=True,
        stdout=io.StringIO(),
    )
    assert code == 0
    assert opened_desktop == [serve_url("127.0.0.1", DEFAULT_PORT)]
    assert opened_browser == []


def test_frozen_browser_flag_opens_browser():
    opened_desktop = []
    opened_browser = []
    code = main(
        ["--browser"],
        find_port=lambda: DEFAULT_PORT,
        run_uvicorn=lambda **kwargs: None,
        open_browser=opened_browser.append,
        open_desktop=opened_desktop.append,
        is_frozen_app=True,
        stdout=io.StringIO(),
    )
    assert code == 0
    assert opened_browser == [serve_url("127.0.0.1", DEFAULT_PORT)]
    assert opened_desktop == []


def test_desktop_missing_webview_message():
    stdout = io.StringIO()
    real = importlib.import_module

    def importer(name):
        if name == "webview":
            raise ImportError(name)
        return real(name)

    code = main(
        ["--desktop"],
        importer=importer,
        find_port=lambda: DEFAULT_PORT,
        run_uvicorn=lambda **kwargs: None,
        stdout=stdout,
    )
    assert code == 1
    assert DESKTOP_MISSING_MESSAGE in stdout.getvalue()
    assert "Traceback" not in stdout.getvalue()


def test_readme_prefers_module_launch():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "python3 -m backend.app" in readme
    assert "uvicorn backend.app.main:app --reload --port 4173" in readme


def test_run_sh_exists_and_delegates():
    script = REPO_ROOT / "run.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert ".venv" in text
    assert 'python3 -m backend.app "$@"' in text


def test_run_bat_exists_and_delegates():
    script = REPO_ROOT / "run.bat"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert ".venv" in text
    assert "python -m backend.app" in text


def test_readme_documents_desktop_packaging():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "build.ps1" in readme
    assert "LearningLoop.exe" in readme
    assert "requirements-desktop.txt" in readme
    assert "--desktop" in readme


def test_index_uses_local_fonts():
    html = (REPO_ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html
    assert "/vendor/fonts/fonts.css" in html
    fonts_dir = REPO_ROOT / "frontend/vendor/fonts"
    assert (fonts_dir / "fonts.css").is_file()
    assert (fonts_dir / "plus-jakarta-sans-latin-wght-normal.woff2").is_file()
    assert (fonts_dir / "patrick-hand-latin-400-normal.woff2").is_file()
    assert (fonts_dir / "jetbrains-mono-latin-wght-normal.woff2").is_file()


def test_packaging_entry_and_spec_exist():
    assert (REPO_ROOT / "packaging/entry.py").is_file()
    spec = (REPO_ROOT / "packaging/learning-loop.spec").read_text(encoding="utf-8")
    assert "LearningLoop" in spec
    assert "frontend" in spec
    build_ps1 = (REPO_ROOT / "packaging/build.ps1").read_text(encoding="utf-8")
    assert "Windows_NT" in build_ps1
    assert ".venv-desktop" in build_ps1
    assert "LearningLoop.exe" in build_ps1
    assert '"3.12"' in build_ps1
    assert '"3.13"' in build_ps1
    assert "3.10+" in build_ps1
    assert (REPO_ROOT / "packaging/build-macos.sh").is_file()
    assert (REPO_ROOT / "frontend/icon.ico").is_file()
    assert (REPO_ROOT / "frontend/icon.png").is_file()
