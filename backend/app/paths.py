"""Resolve bundled resources versus the writable user data directory."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DATA_NAME = "LearningLoop"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root(*, frozen: bool | None = None, meipass: str | None = None) -> Path:
    use_frozen = is_frozen() if frozen is None else frozen
    extracted = meipass if meipass is not None else getattr(sys, "_MEIPASS", None)
    if use_frozen and extracted:
        return Path(extracted)
    return Path(__file__).resolve().parents[2]


def frontend_dir(*, frozen: bool | None = None, meipass: str | None = None) -> Path:
    return resource_root(frozen=frozen, meipass=meipass) / "frontend"


def window_icon_path(
    *,
    platform: str | None = None,
    frozen: bool | None = None,
    meipass: str | None = None,
) -> Path | None:
    frontend = frontend_dir(frozen=frozen, meipass=meipass)
    plat = platform if platform is not None else sys.platform
    if plat == "win32":
        ico = frontend / "icon.ico"
        if ico.is_file():
            return ico
    png = frontend / "icon.png"
    if png.is_file():
        return png
    svg = frontend / "favicon.svg"
    if svg.is_file():
        return svg
    return None


def user_data_dir(
    *,
    platform: str | None = None,
    environ: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    plat = platform if platform is not None else sys.platform
    env = environ if environ is not None else os.environ
    home_dir = home if home is not None else Path.home()
    if plat == "win32":
        base = env.get("LOCALAPPDATA") or str(home_dir / "AppData" / "Local")
        return Path(base) / APP_DATA_NAME
    if plat == "darwin":
        return home_dir / "Library" / "Application Support" / APP_DATA_NAME
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "learning-loop"
    return home_dir / ".local" / "share" / "learning-loop"


def default_data_dir(
    *,
    frozen: bool | None = None,
    environ: dict[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    env = environ if environ is not None else os.environ
    override = env.get("LEARNING_LOOP_DATA_DIR")
    if override:
        return Path(override)
    if is_frozen() if frozen is None else frozen:
        return user_data_dir(environ=env, platform=platform, home=home)
    return resource_root(frozen=False) / "data"
