from pathlib import Path

from backend.app.paths import (
    APP_DATA_NAME,
    default_data_dir,
    frontend_dir,
    resource_root,
    user_data_dir,
    window_icon_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_source_data_dir_is_repo_data(monkeypatch):
    monkeypatch.delenv("LEARNING_LOOP_DATA_DIR", raising=False)
    assert default_data_dir(frozen=False) == REPO_ROOT / "data"


def test_env_overrides_frozen_and_source_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("LEARNING_LOOP_DATA_DIR", str(tmp_path))
    env = {"LEARNING_LOOP_DATA_DIR": str(tmp_path)}
    assert default_data_dir(frozen=True, environ=env) == tmp_path
    assert default_data_dir(frozen=False, environ=env) == tmp_path


def test_frozen_windows_data_dir(tmp_path):
    home = tmp_path / "home"
    env = {"LOCALAPPDATA": str(tmp_path / "local")}
    assert user_data_dir(platform="win32", environ=env, home=home) == tmp_path / "local" / APP_DATA_NAME
    assert default_data_dir(frozen=True, platform="win32", environ=env, home=home) == tmp_path / "local" / APP_DATA_NAME


def test_frozen_mac_data_dir(tmp_path):
    home = tmp_path / "home"
    path = user_data_dir(platform="darwin", environ={}, home=home)
    assert path == home / "Library" / "Application Support" / APP_DATA_NAME


def test_frozen_resource_root_uses_meipass(tmp_path):
    (tmp_path / "frontend").mkdir()
    assert resource_root(frozen=True, meipass=str(tmp_path)) == tmp_path
    assert frontend_dir(frozen=True, meipass=str(tmp_path)) == tmp_path / "frontend"


def test_window_icon_prefers_ico_on_windows():
    icon = window_icon_path(frozen=False, platform="win32")
    assert icon is not None
    assert icon.name == "icon.ico"


def test_window_icon_png_on_mac():
    icon = window_icon_path(frozen=False, platform="darwin")
    assert icon is not None
    assert icon.name == "icon.png"


def test_frontend_dir_from_source():
    assert frontend_dir(frozen=False) == REPO_ROOT / "frontend"
    assert (frontend_dir(frozen=False) / "index.html").is_file()


def test_app_serves_local_fonts_and_icon(tmp_path):
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    client = TestClient(create_app(data_dir=tmp_path / "data"))
    fonts = client.get("/vendor/fonts/fonts.css")
    assert fonts.status_code == 200
    assert "Plus Jakarta Sans" in fonts.text
    woff = client.get("/vendor/fonts/plus-jakarta-sans-latin-wght-normal.woff2")
    assert woff.status_code == 200
    assert woff.content[:4] == b"wOF2"
    icon = client.get("/icon.png")
    assert icon.status_code == 200
    script = client.get("/js/app.js")
    assert script.status_code == 200
    assert "javascript" in script.headers.get("content-type", "")
