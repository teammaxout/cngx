# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a standalone Cogscope CLI binary.

Bundled dependencies include scipy, frouros, and duckdb so the executable
matches the full CLI/proxy workflow without a separate Python install.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).resolve().parents[1]

block_cipher = None

datas = []
binaries = []
hiddenimports = collect_submodules("cogscope")

for pkg in ("duckdb", "frouros", "scipy", "numpy", "typer", "rich", "httpx", "starlette", "uvicorn"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

hiddenimports += [
    "cogscope.cli.main",
    "cogscope.cli.wrap",
    "cogscope.cli.watch",
    "cogscope.cli.quickstart_cmd",
    "cogscope.proxy.app",
    "cogscope.proxy.server",
    "cogscope.drift.streaming",
    "cogscope.drift.batch",
    "cogscope.storage.database",
    "scipy.special.cython_special",
    "scipy.linalg.cython_blas",
    "scipy.linalg.cython_lapack",
]

a = Analysis(
    [str(root / "cogscope" / "__main__.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter", "pytest", "IPython"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="cogscope",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
