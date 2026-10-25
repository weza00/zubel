# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/Zubel/ (modo carpeta, arranque rápido y carpeta bin/ escribible).
# Uso: pyinstaller zubel.spec   (o python tools/build.py)

# Módulos de Qt que la app no usa: se excluyen para reducir el tamaño.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtHttpServer", "PySide6.QtSpatialAudio",
    "tkinter", "unittest", "pydoc",
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/zubel.png", "assets")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtMultimedia", "PySide6.QtNetwork"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Zubel",
    icon="assets/zubel.ico",
    console=False,
    disable_windowed_traceback=False,
    upx=False,
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Zubel",
)
