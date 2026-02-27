#include "stress_cpu.hpp"
#include <thread>
#include <vector>
#include <chrono>
#include <atomic>

namespace stress {

namespace {

unsigned int hardware_concurrency() {
    // Exactly match the thread count to the logical core count. 
    // This perfectly fills the CPU without thrashing the OS scheduler.
    unsigned int n = std::thread::hardware_concurrency();
    return n > 0 ? n : 1;
}

// CPU-bound work: 8-way independent FMA chains for maximum ALU saturation
void cpu_busy_loop(std::atomic<bool>& stop_flag) {
    // We use 8 independent accumulators to perfectly saturate the 
    // superscalar pipeline with zero stall cycles, maximizing power draw.
    double d1 = 1.1, d2 = 1.2, d3 = 1.3, d4 = 1.4;
    double d5 = 1.5, d6 = 1.6, d7 = 1.7, d8 = 1.8;

    const int inner_iters = 100000;
    
    while (!stop_flag.load(std::memory_order_relaxed)) {
        for (int i = 0; i < inner_iters; ++i) {
            // Unrolled, branchless math forces the Floating Point Units to 100% capacity
            d1 = d1 * 1.0000001 + 0.0000001;
            d2 = d2 * 1.0000002 + 0.0000002;
            d3 = d3 * 1.0000003 + 0.0000003;
            d4 = d4 * 1.0000004 + 0.0000004;
            d5 = d5 * 1.0000005 + 0.0000005;
            d6 = d6 * 1.0000006 + 0.0000006;
            d7 = d7 * 1.0000007 + 0.0000007;
            d8 = d8 * 1.0000008 + 0.0000008;
        }
        
        // Reset values before they hit Infinity/NaN to keep power draw high
        if (d1 > 1e100) {
            d1 = 1.1; d2 = 1.2; d3 = 1.3; d4 = 1.4;
            d5 = 1.5; d6 = 1.6; d7 = 1.7; d8 = 1.8;
        }
        
        // A single volatile sink at the very end forces the compiler to compute 
        // everything in registers, preventing dead-code elimination.
        volatile double sink = d1 + d2 + d3 + d4 + d5 + d6 + d7 + d8;
        (void)sink;
    }
}

} // namespace

void run_cpu_stress(std::atomic<bool>& stop_flag) {
    const unsigned int n_threads = hardware_concurrency();
    std::vector<std::thread> threads;
    threads.reserve(n_threads);

    // Stripped out OS-level priority escalations. 
    // The threads will run at standard priority, allowing the OS to preempt 
    // them just enough to keep the UI and mouse responsive.

    for (unsigned int i = 0; i < n_threads; ++i) {
        threads.emplace_back(cpu_busy_loop, std::ref(stop_flag));
    }
    for (auto& t : threads) {
        if (t.joinable()) t.join();
    }
}

} // namespace stress