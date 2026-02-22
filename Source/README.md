## Build without CMake (recommended if CMake is not installed)

You need **Visual Studio** (or **Build Tools for Visual Studio**) with “Desktop development with C++” installed.

1. Open a **Command Prompt** or **PowerShell**.
2. Go to this folder and run:

```bat
cd stress_backend
build.bat
```

The script finds Visual Studio and builds `stress_bench.exe` into `stress_backend\build\stress_bench.exe` (CPU + RAM stress only; no GPU/VRAM without CUDA/CMake).

If you use **“x64 Native Tools Command Prompt for VS”** from the Start Menu, run these from that window. **Important:** the first `cd` must go to **your project’s** `stress_backend` folder, not the Visual Studio folder:

```bat
cd C:\Users\User\Desktop\Stufffz\All-in-one-Benchmark\stress_backend
mkdir build
cd build
cl ..\main.cpp ..\stress_cpu.cpp ..\stress_ram.cpp /Fe:stress_bench.exe /EHsc /std:c++17
```

(Replace the path in the first line if your project is somewhere else.)

If you see **“Cannot open source file”**, you are in the wrong directory—make sure you `cd` to the project’s `stress_backend` folder (where `main.cpp` lives), then `mkdir build`, `cd build`, then run the `cl` command.

## Build with CMake (CPU + RAM)

If CMake is installed and on your PATH:

```bash
cd stress_backend
cmake -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

Or with Ninja:

```bash
cd stress_backend
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

The executable will be at `stress_backend/build/Release/stress_bench.exe` (or `build/stress_bench.exe` with Ninja).

## Build with GPU/VRAM (CUDA)

By default the project **skips CUDA** so it configures and builds without needing a CUDA toolset (you get CPU + RAM stress only). To enable GPU/VRAM stress:

1. Install [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) and set **`CUDA_PATH`** (e.g. `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1`).
2. Use Visual Studio 2022 (CUDA 13.x supports VS 2019–2022; VS 18 can cause cudafe++ crashes).
3. **Visual Studio generator:** you must pass the CUDA toolset with **`-T "cuda=..."`** or CMake will report “No CUDA toolset found”:

```bat
cmake -B build -G "Visual Studio 17 2022" -A x64 -DSTRESS_SKIP_CUDA=OFF -T "cuda=%CUDA_PATH%"
cmake --build build --config Release
```

If `CUDA_PATH` is set, the first line uses it. Otherwise use the version number, e.g. `-T cuda=13.1`.

**Ninja** (no `-T` needed):

```bat
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRESS_SKIP_CUDA=OFF
cmake --build build
```

If you see “No CUDA toolset found” or other CUDA errors, build without CUDA (default): omit `-DSTRESS_SKIP_CUDA=OFF` to get CPU + RAM only.

## Usage (standalone)

```text
stress_bench [--cpu] [--ram] [--gpu] [--vram]
```

At least one option is required. The process runs until it is terminated (the Python GUI starts it and kills it when the dashboard closes).

## What each option does

- **--cpu**  Uses one thread per logical core doing sustained floating-point work to max out CPU.
- **--ram**  Allocates and touches memory up to ~90% of available physical RAM.
- **--gpu**  (CUDA) Runs a compute kernel repeatedly to keep the GPU busy.
- **--vram** (CUDA) Allocates device memory up to ~90% of free VRAM.

The Python launcher (`stress_runner.py`) starts this executable with the flags that match the checkboxes selected in the selection dialog. It looks for `stress_bench.exe` in `stress_backend/build/Debug/`, `stress_backend/build/Release/`, or `stress_backend/build/stress_bench.exe`. Run `main.py` from the **project root** (the folder that contains `main.py` and `stress_backend`).
