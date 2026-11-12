# -*- mode: python ; coding: utf-8 -*-
# PyInstaller configuration for SnapMitra (one-folder build, windowed, with logo icon).
#   pyinstaller --noconfirm SnapMitra.spec
# Needs ./models/u2net.onnx and ./models/face_detector.onnx (tools/fetch_model.py downloads them).
from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets"), ("models", "models")]      # logo/icons/fonts + AI models are bundled -> fully offline
binaries, hiddenimports = [], ["ui_textdialog", "PIL.ImageTk", "PIL._tkinter_finder", "win32print", "win32ui", "win32timezone"]
for pkg in ("onnxruntime", "tkinterdnd2", "sv_ttk"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["main.py"], pathex=["."], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    # keep the app small and fast: none of these are used (and OpenCV / rembg must NOT come back)
    excludes=["cv2", "rembg", "numba", "llvmlite", "scipy", "skimage", "matplotlib", "pandas", "IPython", "pytest", "pooch"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="SnapMitra",
    icon="assets/snapmitra.ico",          # Windows executable icon (the SnapMitra logo)
    console=False, disable_windowed_traceback=False, upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SnapMitra")
