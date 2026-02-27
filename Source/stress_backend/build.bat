@echo off
setlocal
cd /d "%~dp0"

set "BUILD_DIR=build"
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%"
cd "%BUILD_DIR%"

:: Find Visual Studio (2019/2022 typical)
set "VCVARS="
for %%v in (2022 2019) do (
  for %%e in (Enterprise Professional Community BuildTools) do (
    if exist "C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvars64.bat" (
      set "VCVARS=C:\Program Files\Microsoft Visual Studio\%%v\%%e\VC\Auxiliary\Build\vcvars64.bat"
      goto :found
    )
  )
)
:found

if "%VCVARS%"=="" (
  echo vcvars64.bat not found. Install "Desktop development with C++" from Visual Studio or Build Tools.
  echo Or open "x64 Native Tools Command Prompt for VS" and run: cl ..\main.cpp ..\stress_cpu.cpp ..\stress_ram.cpp /Fe:stress_bench.exe /EHsc /std:c++17
  exit /b 1
)

call "%VCVARS%" >nul 2>&1
echo Building stress_bench.exe (CPU + RAM stress)...
rem /MT = static CRT so the exe runs on any PC without installing VC++ Redistributable
cl /nologo /EHsc /std:c++17 /O2 /MT /Fe:stress_bench.exe ..\main.cpp ..\stress_cpu.cpp ..\stress_ram.cpp
if errorlevel 1 exit /b 1
echo Done: %CD%\stress_bench.exe
cd ..
exit /b 0
