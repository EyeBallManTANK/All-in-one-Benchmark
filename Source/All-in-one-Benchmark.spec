# PyInstaller spec for All-in-One Benchmark
# Run: pyinstaller All-in-one-Benchmark.spec
# Requires: build stress_bench.exe first (see README or PACKAGING.md)

import os

# Include the C++ stress backend (build it first: stress_backend\build.bat or CMake Release)
_stress_exe = None
for candidate in [
    os.path.join("stress_backend", "build", "Release", "stress_bench.exe"),
    os.path.join("stress_backend", "build", "Debug", "stress_bench.exe"),
    os.path.join("stress_backend", "build", "stress_bench.exe"),
]:
    if os.path.isfile(candidate):
        _stress_exe = (candidate, ".")
        break
if _stress_exe is None:
    raise FileNotFoundError(
        "stress_bench.exe not found. Build it first:\n"
        "  cd stress_backend && build.bat\n"
        "  or: cmake -B build -G \"Visual Studio 17 2022\" -A x64 && cmake --build build --config Release"
    )

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[_stress_exe],
    datas=[],
    hiddenimports=["PyQt6.QtCore", "PyQt6.QtWidgets", "PyQt6.QtGui", "pyqtgraph", "psutil"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="All-in-one-Benchmark",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window for GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
