# Building a single .exe for GitHub

This produces **one executable** (`All-in-one-Benchmark.exe`) that you can put in a GitHub Release. It bundles the Python GUI and the C++ stress backend.

## Making the exe run on any computer

So that users can **drop the exe on any PC and run it with no extra installs**:

1. **Build the stress backend without CUDA** (default). That way the exe does not require NVIDIA drivers or CUDA. CPU and RAM stress work everywhere; GPU/VRAM stress options are only available if you build with CUDA and the user has an NVIDIA GPU.
2. **Use the built-in static CRT** so the stress process does not need the Visual C++ Redistributable. The CMake build and `build.bat` are already set up for this. If the stress backend still exits right after launch (e.g. old build without static CRT), the app will suggest installing the VC++ Redistributable.
3. **Temperatures use only built-in Windows and drivers:** CPU temp comes from Windows WMI (MSAcpi_ThermalZoneTemperature; works on many laptops, often missing on desktops). GPU temp and GPU/VRAM usage come from **nvidia-smi**, which is present when NVIDIA drivers are installed (no extra software). On AMD/Intel GPUs, GPU/VRAM graphs show 0% and --°C.

If you build with CUDA for GPU/VRAM stress, the exe will only run correctly on PCs with NVIDIA drivers; use a CPU+RAM-only build for maximum portability.

## Prerequisites

- **Python 3.10+** with pip
- **Visual Studio** (or Build Tools) with C++ desktop workload — to build the stress backend
- **PyInstaller** — only for building the exe

## Step 1: Install Python dependencies

From the project root:

```bat
pip install -r requirements.txt
```

No optional packages. The built exe uses only Windows WMI and nvidia-smi (with NVIDIA driver) for temps; end users install nothing.

## Step 2: Build the C++ stress backend

You must build `stress_bench.exe` first so it can be bundled into the final exe.

**Option A — Quick (CPU + RAM only):**

```bat
cd stress_backend
build.bat
cd ..
```

This creates `stress_backend\build\stress_bench.exe`.

**Option B — CMake Release (recommended for distribution):**

```bat
cd stress_backend
cmake -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
cd ..
```

This creates `stress_backend\build\Release\stress_bench.exe`.

**Option C — With GPU/VRAM (CUDA):**  
See `stress_backend/README.md` for CUDA build instructions, then use the Release exe path in the spec if needed.

## Step 3: Install PyInstaller

```bat
pip install pyinstaller
```

## Step 4: Build the single .exe

From the **project root** (folder that contains `main.py` and `stress_backend`):

```bat
pyinstaller All-in-one-Benchmark.spec
```

Output:

- **dist/All-in-one-Benchmark.exe** — single executable to distribute

If the spec reports that `stress_bench.exe` was not found, complete Step 2 and run Step 4 again.

## Step 5: Test and upload

1. Run `dist\All-in-one-Benchmark.exe` on your machine and confirm the dashboard and stress options work.
2. For GitHub: create a **Release**, upload `All-in-one-Benchmark.exe` as an asset, and add a short note (e.g. “Windows x64. Run and choose CPU/RAM/GPU/VRAM stress, then view the dashboard.”).

## One-folder build (optional)

If you prefer one folder with the exe plus dependencies (e.g. for easier debugging or smaller updates), edit the spec: change the `EXE(...)` block to use `Tree` and `COLLECT` for a onedir build, or run:

```bat
pyinstaller --onedir --windowed --name All-in-one-Benchmark main.py
```

Then manually copy `stress_bench.exe` into the generated `dist/All-in-one-Benchmark/` folder. The app looks for `stress_bench.exe` next to the main exe when packaged.

## Notes

- **Antivirus:** Packed executables are sometimes flagged. You can sign the exe (code signing) to reduce false positives.
- **Size:** The single exe is large (PyQt6 + Python runtime). This is normal for PyInstaller one-file builds.
- **CUDA:** If the stress backend was built with CUDA, the exe needs NVIDIA drivers on the target PC. For "run anywhere," build without CUDA (default).
- **VC++ Redist:** The stress backend is built with the static CRT, so users do not need to install the Visual C++ Redistributable. If the stress process exits right after launch, the app will suggest installing the VC++ Redistributable (x64).
