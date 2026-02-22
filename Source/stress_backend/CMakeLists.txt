cmake_minimum_required(VERSION 3.18)
project(stress_bench LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

# Optional CUDA (NVIDIA). Default OFF = skip CUDA so build works without CUDA toolset. Set OFF to enable GPU/VRAM.
option(STRESS_SKIP_CUDA "Skip CUDA build (default ON; set OFF to enable GPU/VRAM when CUDA is installed)" ON)
set(STRESS_HAVE_CUDA OFF)
if(NOT STRESS_SKIP_CUDA)
  if(DEFINED ENV{CUDA_PATH})
    set(CMAKE_CUDA_COMPILER "$ENV{CUDA_PATH}/bin/nvcc.exe")
  endif()
  find_package(CUDAToolkit QUIET)
  if(CUDAToolkit_FOUND)
    # Visual Studio generator requires the CUDA toolset via -T cuda=... (see README)
    if(CMAKE_GENERATOR MATCHES "Visual Studio" AND NOT CMAKE_GENERATOR_TOOLSET MATCHES "cuda=")
      if(DEFINED ENV{CUDA_PATH})
        message(FATAL_ERROR "With the Visual Studio generator you must pass the CUDA toolset.\n"
          "Re-run cmake with: -T \"cuda=$ENV{CUDA_PATH}\"\n"
          "Example:\n  cmake -B build -G \"Visual Studio 17 2022\" -A x64 -DSTRESS_SKIP_CUDA=OFF -T \"cuda=$ENV{CUDA_PATH}\"")
      else()
        message(FATAL_ERROR "With the Visual Studio generator you must pass the CUDA toolset.\n"
          "Re-run cmake with: -T cuda=13.1  (or your CUDA version)\n"
          "Or set CUDA_PATH and use: -T \"cuda=%CUDA_PATH%\"")
      endif()
    endif()
    # Allow Visual Studio newer than 2022 (e.g. VS 18) as host compiler
    set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -allow-unsupported-compiler")
    enable_language(CUDA)
    set(STRESS_HAVE_CUDA ON)
    message(STATUS "CUDA found: building GPU/VRAM stress")
  else()
    message(STATUS "CUDA not found: building CPU/RAM stress only")
  endif()
else()
  message(STATUS "CUDA skipped (STRESS_SKIP_CUDA=ON): building CPU/RAM stress only")
endif()

add_executable(stress_bench
  main.cpp
  stress_cpu.cpp
  stress_ram.cpp
)

if(STRESS_HAVE_CUDA)
  target_sources(stress_bench PRIVATE stress_gpu.cu)
  target_compile_definitions(stress_bench PRIVATE STRESS_HAVE_CUDA)
  set_target_properties(stress_bench PROPERTIES
    CUDA_SEPARABLE_COMPILATION ON
    CUDA_ARCHITECTURES "75;80;86;89"
  )
endif()

target_include_directories(stress_bench PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# Windows: avoid console window when launched from Python (optional)
if(WIN32)
  # Keep console for debugging; set to WIN32 to hide console
  # set_target_properties(stress_bench PROPERTIES WIN32_EXECUTABLE ON)
endif()
