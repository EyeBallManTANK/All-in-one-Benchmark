/**
 * Stress benchmark backend. Run with --cpu, --ram, --gpu, --vram (any combination).
 * Runs until the process is terminated (e.g. by the Python launcher when the dashboard closes).
 */
#include "stress_cpu.hpp"
#include "stress_ram.hpp"
#include <atomic>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#ifdef STRESS_HAVE_CUDA
extern "C" void run_gpu_stress(std::atomic<bool>* stop_flag);
extern "C" void run_vram_stress(std::atomic<bool>* stop_flag);
#endif

static void usage(const char* prog) {
    std::cerr << "Usage: " << prog << " [--cpu] [--ram] [--gpu] [--vram]\n"
              << "  At least one option must be given.\n"
              << "  Process runs until killed (e.g. by parent).\n";
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

#ifdef STRESS_HAVE_CUDA
    (void)0;
#else
    if (do_gpu || do_vram) {
        std::cerr << "Warning: GPU/VRAM not available (build without CUDA). Skipping.\n";
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
#ifdef STRESS_HAVE_CUDA
    if (do_gpu) {
        workers.emplace_back([&stop_gpu]() { run_gpu_stress(&stop_gpu); });
    }
    if (do_vram) {
        workers.emplace_back([&stop_vram]() { run_vram_stress(&stop_vram); });
    }
#endif

    for (auto& w : workers) {
        w.join();
    }

    return 0;
}
