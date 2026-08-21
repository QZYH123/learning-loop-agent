"""Process launcher for `python3 -m backend.app`."""
from __future__ import annotations

import argparse
import importlib
import socket
import sys
import threading
import time
import webbrowser

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4173
PORT_RANGE_END = 4179
MISSING_DEPENDENCY_MESSAGE = "缺少运行依赖，请先运行 pip install -r requirements.txt"
PORTS_BUSY_MESSAGE = "4173 到 4179 端口都被占用，无法启动"
REQUIRED_MODULES = (
    "fastapi",
    "uvicorn",
    "httpx",
    "python_multipart",
    "pypdf",
    "docx",
    "pptx",
    "PIL",
    "jsonpatch",
    "reportlab",
)


def check_dependencies(importer=None) -> str | None:
    load = importer or importlib.import_module
    for name in REQUIRED_MODULES:
        try:
            load(name)
        except ImportError:
            return MISSING_DEPENDENCY_MESSAGE
    return None


def port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(
    host: str = DEFAULT_HOST,
    start: int = DEFAULT_PORT,
    end: int = PORT_RANGE_END,
) -> int | None:
    for port in range(start, end + 1):
        if port_is_available(host, port):
            return port
    return None


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 AI 学习工具")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不打开浏览器",
    )
    return parser.parse_args(argv)


def serve_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _open_when_ready(host: str, port: int, url: str, opener) -> None:
    def wait_and_open() -> None:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.2):
                    opener(url)
                    return
            except OSError:
                time.sleep(0.05)

    threading.Thread(target=wait_and_open, daemon=True).start()


def _run_uvicorn(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run("backend.app.main:app", host=host, port=port, reload=False)


def main(
    argv=None,
    *,
    importer=None,
    find_port=None,
    run_uvicorn=None,
    open_browser=None,
    stdout=None,
) -> int:
    out = stdout or sys.stdout
    missing = check_dependencies(importer)
    if missing:
        print(missing, file=out)
        return 1

    args = parse_args(argv)
    port = (find_port or find_available_port)()
    if port is None:
        print(PORTS_BUSY_MESSAGE, file=out)
        return 1

    url = serve_url(DEFAULT_HOST, port)
    if port != DEFAULT_PORT:
        print(f"端口 {DEFAULT_PORT} 已被占用，已改用 {url}", file=out)
    print(f"应用地址：{url}", file=out)

    opener = open_browser or webbrowser.open
    runner = run_uvicorn or _run_uvicorn
    if not args.no_browser:
        if run_uvicorn is None:
            _open_when_ready(DEFAULT_HOST, port, url, opener)
        else:
            opener(url)
    runner(host=DEFAULT_HOST, port=port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
