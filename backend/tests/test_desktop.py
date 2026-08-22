from pathlib import Path

from backend.app.desktop import WINDOW_TITLE, open_desktop_window


class FakeWebview:
    def __init__(self):
        self.created = None
        self.started = None

    def create_window(self, title, url, width=800, height=600, min_size=(100, 100), text_select=False, confirm_close=False, background_color="#fff", easy_drag=True):
        self.created = {
            "title": title,
            "url": url,
            "width": width,
            "height": height,
            "min_size": min_size,
            "text_select": text_select,
            "confirm_close": confirm_close,
            "background_color": background_color,
            "easy_drag": easy_drag,
        }

    def start(self, gui=None):
        self.started = {"gui": gui}


def test_create_window_does_not_receive_icon(tmp_path):
    icon = tmp_path / "app.ico"
    icon.write_bytes(b"ico")
    fake = FakeWebview()
    open_desktop_window("http://127.0.0.1:4173", icon_path=icon, webview_module=fake)
    assert fake.created["title"] == WINDOW_TITLE
    assert fake.created["url"] == "http://127.0.0.1:4173"
    assert fake.created["easy_drag"] is False
    assert "icon" not in fake.created
    assert fake.started is not None


def test_start_receives_icon_when_supported(tmp_path, monkeypatch):
    icon = tmp_path / "app.ico"
    icon.write_bytes(b"ico")

    class StartWithIcon:
        def __init__(self):
            self.created = None
            self.started = None

        def create_window(self, title, url, **kwargs):
            self.created = {"title": title, "url": url, **kwargs}

        def start(self, gui=None, icon=None, private_mode=True, storage_path=None, debug=False):
            self.started = {
                "gui": gui,
                "icon": icon,
                "private_mode": private_mode,
                "storage_path": storage_path,
                "debug": debug,
            }

    fake = StartWithIcon()
    monkeypatch.setattr("backend.app.desktop.sys", type("Sys", (), {"platform": "win32"}))
    storage = tmp_path / "webview"
    open_desktop_window(
        "http://127.0.0.1:4173",
        icon_path=icon,
        storage_path=storage,
        webview_module=fake,
    )
    assert fake.started["icon"] == str(icon)
    assert fake.started["gui"] == "edgechromium"
    assert fake.started["private_mode"] is False
    assert fake.started["storage_path"] == str(storage)
    assert Path(fake.started["icon"]).is_file()
