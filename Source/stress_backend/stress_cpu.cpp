#include "stress_cpu.hpp"
#include <thread>
#include <vector>
#include <chrono>

#ifdef _WIN32
#include <windows.h>
#endif

namespace stress {

namespace {

unsigned int hardware_concurrency() {
    unsigned int n = std::thread::hardware_concurrency();
    return n > 0 ? n : 1;
}

// CPU-bound work: heavy loop so the core stays at ~100% (volatile prevents optimization)
void cpu_busy_loop(std::atomic<bool>& stop_flag) {
    volatile double x = 1.0;
    const int inner_iters = 10000000;  // enough work between stop_flag checks to actually stress
    while (!stop_flag.load(std::memory_order_relaxed)) {
        for (int i = 0; i < inner_iters; ++i) {
            x = x * 1.0000001 + 0.0000001;
            if (x > 1e15) x *= 1e-15;
        }
    }
    (void)x;
}

} // namespace

void run_cpu_stress(std::atomic<bool>& stop_flag) {
    const unsigned int n_threads = hardware_concurrency();
    std::vector<std::thread> threads;
    threads.reserve(n_threads);

#ifdef _WIN32
    // Prefer process affinity so the OS sees real load (optional)
    DWORD_PTR mask = (1ULL << n_threads) - 1;
    SetProcessAffinityMask(GetCurrentProcess(), mask);
#endif

    for (unsigned int i = 0; i < n_threads; ++i) {
        threads.emplace_back(cpu_busy_loop, std::ref(stop_flag));
    }
    for (auto& t : threads) {
        if (t.joinable()) t.join();
    }
}

} // namespace stress
