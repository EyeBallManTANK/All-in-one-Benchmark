/**
 * Stress benchmark backend. Run with --cpu, --ram, --gpu, --vram (any combination).
 * GPU/VRAM: uses CUDA when available (NVIDIA), else OpenCL (AMD/Intel or fallback).
 */
#include "stress_cpu.hpp"
#include "stress_ram.hpp"
#include <atomic>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#ifdef STRESS_HAVE_CUDA
extern "C" int cuda_available(void);
extern "C" void run_gpu_stress(std::atomic<bool>* stop_flag);
extern "C" void run_vram_stress(std::atomic<bool>* stop_flag);
#endif

#ifdef STRESS_HAVE_OPENCL
extern "C" void run_gpu_stress_opencl(std::atomic<bool>* stop_flag);
extern "C" void run_vram_stress_opencl(std::atomic<bool>* stop_flag);
#endif

static void usage(const char* prog) {
    std::cerr << "Usage: " << prog << " [--cpu] [--ram] [--gpu] [--vram]\n"
              << "  At least one option must be given.\n"
              << "  GPU/VRAM: CUDA (NVIDIA) or OpenCL (AMD/Intel).\n";
}

int main(int argc, char* argv[]) {
    bool do_cpu = false, do_ram = false, do_gpu = false, do_vram = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--cpu")  do_cpu = true;
        else if (arg == "--ram")  do_ram = true;
        else if (arg == "--gpu")  do_gpu = true;
        else if (arg == "--vram") do_vram = true;
        else if (arg == "--help" || arg == "-h") {
            usage(argv[0]);
            return 0;
        }
    }

    if (!do_cpu && !do_ram && !do_gpu && !do_vram) {
        usage(argv[0]);
        return 1;
    }

#if !defined(STRESS_HAVE_CUDA) && !defined(STRESS_HAVE_OPENCL)
    if (do_gpu || do_vram) {
        std::cerr << "Warning: GPU/VRAM not available (build with CUDA or OpenCL). Skipping.\n";
        do_gpu = false;
        do_vram = false;
    }
#endif

    // Stop flags (we never set them; process is terminated by parent)
    std::atomic<bool> stop_cpu{false};
    std::atomic<bool> stop_ram{false};
    std::atomic<bool> stop_gpu{false};
    std::atomic<bool> stop_vram{false};

    std::vector<std::thread> workers;

    if (do_cpu) {
        workers.emplace_back([&stop_cpu]() { stress::run_cpu_stress(stop_cpu); });
    }
    if (do_ram) {
        workers.emplace_back([&stop_ram]() { stress::run_ram_stress(stop_ram); });
    }

    // GPU/VRAM: prefer CUDA (NVIDIA) when available, else OpenCL (AMD/Intel)
    bool use_cuda = false;
#ifdef STRESS_HAVE_CUDA
    if (do_gpu || do_vram) {
        use_cuda = (cuda_available() != 0);
    }
#endif

    if (do_gpu) {
#ifdef STRESS_HAVE_CUDA
        if (use_cuda) {
            workers.emplace_back([&stop_gpu]() { run_gpu_stress(&stop_gpu); });
        } else
#endif
#ifdef STRESS_HAVE_OPENCL
        {
            workers.emplace_back([&stop_gpu]() { run_gpu_stress_opencl(&stop_gpu); });
        }
#else
        if (!use_cuda) { (void)stop_gpu; }
#endif
    }
    if (do_vram) {
#ifdef STRESS_HAVE_CUDA
        if (use_cuda) {
            workers.emplace_back([&stop_vram]() { run_vram_stress(&stop_vram); });
        } else
#endif
#ifdef STRESS_HAVE_OPENCL
        {
            workers.emplace_back([&stop_vram]() { run_vram_stress_opencl(&stop_vram); });
        }
#else
        if (!use_cuda) { (void)stop_vram; }
#endif
    }

    for (auto& w : workers) {
        w.join();
    }

    return 0;
}
