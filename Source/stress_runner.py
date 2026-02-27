"""
Launches the C++ stress backend (stress_bench) with the flags selected in the GUI.
Starts the process when the dashboard opens and terminates it when the app exits.
When run as a PyInstaller-packed exe, looks for stress_bench.exe next to the app or in the bundle.
"""
import os
import subprocess
import sys

def _project_root():
    """Project root: when frozen (packaged exe), use bundle dir; else directory of this file."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _exe_path():
    """Path to stress_bench executable. Returns path or None."""
    # 1. Packaged exe: stress_bench.exe is in the same folder as the main exe or in _MEIPASS
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", None)
        app_dir = os.path.dirname(sys.executable)
        for base in (bundle, app_dir):
            if base:
                path = os.path.join(base, "stress_bench.exe")
                if os.path.isfile(path):
                    return path
        return None

    # 2. Development: look in stress_backend/build/...
    root = os.path.dirname(os.path.abspath(__file__))
    configs = ("Debug", "Release", "MinSizeRel", "RelWithDebInfo")
    candidates = [
        os.path.join(root, "stress_backend", "build", cfg, "stress_bench.exe")
        for cfg in configs
    ]
    candidates.extend([
        os.path.join(root, "stress_backend", "build", "stress_bench.exe"),
        os.path.join(root, "stress_backend", "out", "build", "x64-Debug", "stress_bench.exe"),
        os.path.join(root, "stress_backend", "out", "build", "x64-Release", "stress_bench.exe"),
        os.path.join(root, "stress_backend", "stress_bench.exe"),
        os.path.join(root, "stress_backend", "stress_bench"),
    ])
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None

def start_stress(config):
    """
    Start the C++ stress process based on config from SelectionDialog.get_selected().
    config: dict with keys "cpu", "gpu", "ram", "vram" (bool each).
    Returns (process, error_message): process is Popen or None; error_message is str or None
    (e.g. "stress_bench.exe not found" when user selected options but exe missing).
    """
    wants_stress = config.get("cpu") or config.get("gpu") or config.get("ram") or config.get("vram")
    if not wants_stress:
        return None, None

    exe = _exe_path()
    if not exe:
        search = os.path.join(_project_root(), "stress_backend", "build", "Debug", "stress_bench.exe")
        return None, f"Stress backend not found. Build the project and put stress_bench.exe in one of:\n  stress_backend\\build\\Debug\\\n  stress_backend\\build\\Release\\\n(Expected e.g. {search})"

    args = [exe]
    if config.get("cpu"):
        args.append("--cpu")
    if config.get("ram"):
        args.append("--ram")
    if config.get("gpu"):
        args.append("--gpu")
    if config.get("vram"):
        args.append("--vram")

    # Run with exe's directory as cwd so the backend and any DLLs (e.g. CUDA) find paths correctly.
    # On Windows, hide the console window for the stress backend so no cmd popup appears.
    cwd = os.path.dirname(exe)
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        creationflags = 0
    try:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            creationflags=creationflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return process, None
    except Exception as e:
        return None, f"Failed to start stress backend: {e}"

def stop_stress(process):
    """Terminate the stress backend process. process may be None."""
    if process is None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except ProcessLookupError:
            pass
