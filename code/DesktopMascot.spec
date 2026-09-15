from pathlib import Path

project_dir = Path(SPECPATH)

# Windows application metadata
APP_VERSION = "1.0.0.0"

a = Analysis(
    ["main.py"],
    pathex=[
        str(project_dir)
    ],
    binaries=[],
    hiddenimports=[
        "PySide6.QtMultimedia",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(
    a.pure
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DesktopMascot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon=str(project_dir / "icon.ico"),
    version=str(project_dir / "version_info.txt"),
    codesign_identity=None,
    entitlements_file=None,
)