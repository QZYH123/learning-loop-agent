"""Process launcher for `python3 -m backend.app`."""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .desktop import DesktopWindowError, check_desktop_dependency
from .paths import default_data_dir, is_frozen, window_icon_path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4173
PORT_RANGE_END = 4179
MISSING_DEPENDENCY_MESSAGE = "缺少运行依赖，请先运行 pip install -r requirements.txt"
PORTS_BUSY_MESSAGE = "4173 到 4179 端口都被占用，无法启动"
SERVER_START_FAILED_MESSAGE = "本地服务启动失败，请查看日志后重试。"
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
    parser = argparse.ArgumentParser(description="启动静案")
    ui = parser.add_mutually_exclusive_group()
    ui.add_argument(
        "--desktop",
        action="store_true",
        help="用系统窗口打开（打包后的默认方式）",
    )
    ui.add_argument(
        "--browser",
        action="store_true",
        help="用系统浏览器打开（从源码运行时的默认方式）",
    )
    ui.add_argument(
        "--no-browser",
        action="store_true",
        help="只启动本地服务，不打开窗口或浏览器",
    )
    return parser.parse_args(argv)


def serve_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def wait_until_ready(host: str, port: int, timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _open_when_ready(host: str, port: int, url: str, opener) -> None:
    def wait_and_open() -> None:
        if wait_until_ready(host, port):
            opener(url)

    threading.Thread(target=wait_and_open, daemon=True).start()


def _run_uvicorn(host: str, port: int) -> None:
    try:
        import uvicorn

        from backend.app.main import app as asgi_app

        uvicorn.run(asgi_app, host=host, port=port, reload=False, access_log=True, log_config=None)
    except Exception:
        logging.exception("Failed to start local server")
        raise


def _prepare_data_dir() -> Path:
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def configure_logging(data_dir: Path) -> None:
    log_path = data_dir / "logs" / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)


def show_fatal_error(message: str) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "静案", 0x10)
        return
    if sys.platform == "darwin":
        subprocess.run(
            ["osascript", "-e", f'display alert "静案" message {json.dumps(message)} as critical'],
            check=False,
        )
        return
    print(message, file=sys.stderr)


def _open_desktop(url: str) -> None:
    from .desktop import open_desktop_window

    icon = window_icon_path()
    storage = default_data_dir() / "webview"
    open_desktop_window(url, icon_path=icon, storage_path=storage)


def _serve_with_desktop_window(host: str, port: int, url: str, opener, run_uvicorn) -> int:
    error = {"exc": None}

    def runner(**kwargs):
        try:
            run_uvicorn(**kwargs)
        except Exception as exc:
            logging.exception("Failed to start local server")
            error["exc"] = exc

    thread = threading.Thread(target=runner, kwargs={"host": host, "port": port}, daemon=True)
    thread.start()
    if not wait_until_ready(host, port):
        detail = str(error["exc"]) if error["exc"] else ""
        message = SERVER_START_FAILED_MESSAGE if not detail else f"{SERVER_START_FAILED_MESSAGE}\n\n{detail}"
        show_fatal_error(message)
        return 1
    try:
        opener(url)
    except DesktopWindowError as exc:
        show_fatal_error(str(exc))
        return 1
    return 0


def _use_desktop(args: argparse.Namespace, frozen: bool) -> bool:
    if args.no_browser or args.browser:
        return False
    if args.desktop:
        return True
    return frozen


def main(
    argv=None,
    *,
    importer=None,
    find_port=None,
    run_uvicorn=None,
    open_browser=None,
    open_desktop=None,
    is_frozen_app=None,
    stdout=None,
) -> int:
    from multiprocessing import freeze_support

    freeze_support()
    out = stdout or sys.stdout
    missing = check_dependencies(importer)
    if missing:
        print(missing, file=out)
        return 1

    args = parse_args(argv)
    frozen = is_frozen() if is_frozen_app is None else is_frozen_app
    data_dir = _prepare_data_dir()
    desktop = _use_desktop(args, frozen)
    if run_uvicorn is None and (frozen or desktop):
        configure_logging(data_dir)

    if desktop and open_desktop is None:
        desktop_missing = check_desktop_dependency(importer)
        if desktop_missing:
            print(desktop_missing, file=out)
            return 1

    port = (find_port or find_available_port)()
    if port is None:
        print(PORTS_BUSY_MESSAGE, file=out)
        return 1

    url = serve_url(DEFAULT_HOST, port)
    if port != DEFAULT_PORT:
        print(f"端口 {DEFAULT_PORT} 已被占用，已改用 {url}", file=out)
    print(f"应用地址：{url}", file=out)
    logging.info("Serving %s (data dir %s)", url, data_dir)

    runner = run_uvicorn or _run_uvicorn
    if args.no_browser:
        runner(host=DEFAULT_HOST, port=port)
        return 0

    if desktop:
        opener = open_desktop or _open_desktop
        if run_uvicorn is not None:
            runner(host=DEFAULT_HOST, port=port)
            opener(url)
            return 0
        return _serve_with_desktop_window(DEFAULT_HOST, port, url, opener, runner)

    opener = open_browser or webbrowser.open
    if run_uvicorn is None:
        _open_when_ready(DEFAULT_HOST, port, url, opener)
    else:
        opener(url)
    runner(host=DEFAULT_HOST, port=port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
