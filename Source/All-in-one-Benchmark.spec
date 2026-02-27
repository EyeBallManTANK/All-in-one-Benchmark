# PyInstaller spec for All-in-One Benchmark
# Run: pyinstaller All-in-one-Benchmark.spec
# Requires: build stress_bench.exe first; put LibreHardwareMonitorLib.dll in project root (or adjust path below).
# Temperatures and GPU/VRAM load come from LibreHardwareMonitorLib.dll only.

import os
import glob

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

# LibreHardwareMonitorLib.dll: run pyinstaller from project root with DLL in that folder
_lhm_dll = "LibreHardwareMonitorLib.dll"
_binaries = [_stress_exe]

if os.path.isfile(_lhm_dll):
    _binaries.append((os.path.abspath(_lhm_dll), "."))
    
    # FIX: Grab all the C# System dependency DLLs required by LHM
    for sys_dll in glob.glob("System.*.dll"):
        _binaries.append((os.path.abspath(sys_dll), "."))
else:
    raise FileNotFoundError(
        "LibreHardwareMonitorLib.dll not found. Place it in the project root and run: pyinstaller All-in-one-Benchmark.spec"
    )

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=_binaries,
    datas=[],
    hiddenimports=["PyQt6.QtCore", "PyQt6.QtWidgets", "PyQt6.QtGui", "pyqtgraph", "psutil", "clr"],
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
    console=False,  # NOTE: Change to True temporarily if you still need to debug crashes
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)