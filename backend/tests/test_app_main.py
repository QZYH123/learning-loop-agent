import io
import socket
from pathlib import Path

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
