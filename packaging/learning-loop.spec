# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

spec_root = Path(SPECPATH).resolve()
repo_root = spec_root.parent

datas = [(str(repo_root / "frontend"), "frontend")]
binaries = []
hiddenimports = collect_submodules("backend")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

for pkg in (
    "uvicorn",
    "fastapi",
    "starlette",
    "webview",
    "reportlab",
    "docx",
    "pptx",
    "pypdf",
    "PIL",
    "jsonpatch",
    "multipart",
    "pythonnet",
    "clr_loader",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

icon_ico = spec_root / "icons" / "app.ico"
icon_icns = spec_root / "icons" / "app.icns"
icon_png = spec_root / "icons" / "app.png"
exe_icon = str(icon_ico) if icon_ico.is_file() else None

a = Analysis(
    [str(spec_root / "entry.py")],
    pathex=[str(repo_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "scipy", "pandas"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LearningLoop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=exe_icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LearningLoop",
)

if sys.platform == "darwin":
    bundle_icon = icon_icns if icon_icns.is_file() else icon_png
    app = BUNDLE(
        coll,
        name="LearningLoop.app",
        icon=str(bundle_icon) if bundle_icon.is_file() else None,
        bundle_identifier="app.learningloop.desktop",
        info_plist={
            "CFBundleDisplayName": "AI 学习工具",
            "CFBundleName": "LearningLoop",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
