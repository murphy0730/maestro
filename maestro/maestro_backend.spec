# maestro/maestro_backend.spec — PyInstaller onefolder freeze of the backend sidecar.
# Entry: src/maestro/sidecar_entry.py (reads MAESTRO_BACKEND_PORT, binds 127.0.0.1).
# Output: dist/backend/MaestroBackend + dist/backend/_internal/ (electron-builder
# copies this tree via extraResources → <resources>/backend/).
#
# Build: cd maestro && .venv/bin/python -m PyInstaller maestro_backend.spec --noconfirm
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# Heavy native deps — collect all their data files + binaries + submodules.
for pkg in ("ortools", "chromadb"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# onnxruntime is only pulled by chromadb's *default* embedding function; the
# backend uses an external EMBED_* endpoint, so onnxruntime may be absent.
# Collect it only if installed.
try:
    import onnxruntime  # noqa: F401

    d, b, h = collect_all("onnxruntime")
    datas += d
    binaries += b
    hiddenimports += h
except ImportError:
    pass

# uvicorn internals are imported lazily (string refs); ensure they're frozen.
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

a = Analysis(
    ["src/maestro/sidecar_entry.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MaestroBackend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # --windowed: no terminal window (Electron captures stdio)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="backend",  # → dist/backend/
)
