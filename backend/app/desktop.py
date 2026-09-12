"""Native window around the local HTTP app."""
from __future__ import annotations

import importlib
import inspect
import logging
import os
import sys
from pathlib import Path

WINDOW_TITLE = "静案"
DESKTOP_MISSING_MESSAGE = "缺少桌面窗口依赖，请先运行 pip install -r requirements-desktop.txt"
WEBVIEW2_MESSAGE = (
    "需要 Microsoft Edge WebView2 才能打开窗口。"
    "请安装 WebView2 运行时后重试：https://aka.ms/webview2install"
)


class DesktopWindowError(RuntimeError):
    """Raised when the system webview cannot be opened."""


def check_desktop_dependency(importer=None) -> str | None:
    load = importer or importlib.import_module
    try:
        load("webview")
    except ImportError:
        return DESKTOP_MISSING_MESSAGE
    return None


def _accepted_kwargs(func, values: dict) -> dict:
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return dict(values)
    if any(item.kind == inspect.Parameter.VAR_KEYWORD for item in params.values()):
        return dict(values)
    return {key: value for key, value in values.items() if key in params}


def open_desktop_window(
    url: str,
    icon_path: str | Path | None = None,
    storage_path: str | Path | None = None,
    webview_module=None,
) -> None:
    try:
        webview = webview_module or importlib.import_module("webview")
    except ImportError as exc:
        raise DesktopWindowError(DESKTOP_MISSING_MESSAGE) from exc

    window_kwargs = _accepted_kwargs(
        webview.create_window,
        {
            "title": WINDOW_TITLE,
            "url": url,
            "width": 1400,
            "height": 900,
            "min_size": (960, 640),
            "text_select": True,
            "confirm_close": False,
            "background_color": "#efe9da",
            # Framed window: Edge's default easy_drag captures every mousedown.
            "easy_drag": False,
        },
    )
    window = webview.create_window(**window_kwargs)
    if window is not None and getattr(window, "events", None) is not None:
        def _on_loaded():
            current = url
            try:
                getter = getattr(window, "get_current_url", None)
                if callable(getter):
                    current = getter() or url
            except Exception:
                logging.exception("WebView loaded but current URL is unavailable")
            logging.info("WebView loaded %s", current)

        loaded = getattr(window.events, "loaded", None)
        if loaded is not None and hasattr(loaded, "__iadd__"):
            loaded += _on_loaded

    icon = None
    if icon_path:
        path = Path(icon_path)
        if path.is_file():
            icon = str(path)
    data_dir = Path(storage_path) if storage_path else None
    if data_dir:
        data_dir.mkdir(parents=True, exist_ok=True)
    start_values = {
        "private_mode": False,
        "debug": os.environ.get("LEARNING_LOOP_DEBUG") == "1",
    }
    if sys.platform == "win32":
        start_values["gui"] = "edgechromium"
    if icon:
        start_values["icon"] = icon
    if data_dir:
        start_values["storage_path"] = str(data_dir)
    start_kwargs = _accepted_kwargs(webview.start, start_values)
    try:
        webview.start(**start_kwargs)
    except Exception as exc:
        detail = str(exc).lower()
        if sys.platform == "win32" or "webview2" in detail or "edgechromium" in detail:
            raise DesktopWindowError(WEBVIEW2_MESSAGE) from exc
        raise DesktopWindowError(f"无法打开桌面窗口：{exc}") from exc
