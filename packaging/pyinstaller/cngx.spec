# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a standalone cngx CLI binary.

Bundled dependencies include scipy, frouros, duckdb, and pydantic so the
executable matches the full CLI/proxy workflow without a separate Python install.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

root = Path(SPECPATH).resolve().parents[1]

block_cipher = None

datas = []
binaries = []
hiddenimports = collect_submodules("cngx")

# Required packages. Fail the build if a critical one cannot be collected.
REQUIRED = (
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "annotated_types",
    "typing_extensions",
)
OPTIONAL = (
    "duckdb",
    "frouros",
    "scipy",
    "numpy",
    "typer",
    "rich",
    "httpx",
    "anyio",
    "httpcore",
    "h11",
    "idna",
    "certifi",
    "sniffio",
    "starlette",
    "uvicorn",
    "yaml",
    "fastapi",
    "jinja2",
    "holdout",
    "openai",
    "dotenv",
    "anthropic",
    "click",
    "shellingham",
)

for pkg in REQUIRED + OPTIONAL:
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as exc:
        if pkg in REQUIRED:
            raise RuntimeError(f"PyInstaller collect_all failed for required package {pkg}: {exc}") from exc

# Metadata is needed for some importlib.metadata lookups at runtime.
for meta_pkg in ("pydantic", "pydantic_core", "pydantic-settings", "cngx"):
    try:
        datas += copy_metadata(meta_pkg)
    except Exception:
        pass

hiddenimports += [
    "cngx.cli.main",
    "cngx.cli.wrap",
    "cngx.cli.watch",
    "cngx.cli.quickstart_cmd",
    "cngx.cli.check_cmd",
    "cngx.proxy.app",
    "cngx.proxy.server",
    "cngx.proxy.analysis",
    "cngx.drift.streaming",
    "cngx.drift.batch",
    "cngx.storage.database",
    "cngx.core.config",
    "cngx.core.models",
    "pydantic",
    "pydantic_core",
    "pydantic_core._pydantic_core",
    "pydantic_settings",
    "scipy.special.cython_special",
    "scipy.linalg.cython_blas",
    "scipy.linalg.cython_lapack",
]

a = Analysis(
    [str(root / "cngx" / "__main__.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "tkinter",
        "pytest",
        "IPython",
        "torch",
        "torchvision",
        "torchaudio",
        "transformers",
        "sentence_transformers",
        "pandas",
        "tensorflow",
        "sklearn",
        "skimage",
    ],
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
    name="cngx",
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
