#include "stress_ram.hpp"
#include <thread>
#include <vector>
#include <chrono>
#include <cstdint>
#include <atomic>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#elif defined(__linux__) || defined(__APPLE__)
#include <unistd.h>
#endif

namespace stress {

namespace {

// Dropped to 85% to absolutely prevent the OS from thrashing the Pagefile/Swap.
// This ensures maximum RAM load while keeping your mouse and UI completely responsive.
constexpr double TARGET_FRACTION = 0.85; 
constexpr size_t CHUNK_SIZE = 64 * 1024 * 1024; // 64 MiB

#ifdef _WIN32
size_t get_available_ram_bytes() {
    MEMORYSTATUSEX ms = {};
    ms.dwLength = sizeof(ms);
    if (!GlobalMemoryStatusEx(&ms)) return 0;
    return static_cast<size_t>(ms.ullAvailPhys);
}
#else
size_t get_available_ram_bytes() {
    long pages = sysconf(_SC_AVPHYS_PAGES);
    long page_size = sysconf(_SC_PAGE_SIZE);
    if (pages > 0 && page_size > 0) {
        return static_cast<size_t>(pages) * static_cast<size_t>(page_size);
    }
    return 0;
}
#endif

// The worker thread that hammers a specific memory block
void hammer_memory_chunk(uint64_t* memory, size_t num_elements, std::atomic<bool>& stop_flag) {
    // Classic Memtest alternating bit patterns to stress electrical states
    const uint64_t pattern_1 = 0x5555555555555555ULL; // 01010101...
    const uint64_t pattern_2 = 0xAAAAAAAAAAAAAAAAULL; // 10101010...

    while (!stop_flag.load(std::memory_order_relaxed)) {
        // Pass 1: Aggressive unrolled WRITE of Pattern 1
        for (size_t i = 0; i < num_elements; i += 8) {
            // Check flag frequently so the thread closes instantly when requested
            if (stop_flag.load(std::memory_order_relaxed)) return; 
            
            memory[i]   = pattern_1;
            memory[i+1] = pattern_1;
            memory[i+2] = pattern_1;
            memory[i+3] = pattern_1;
            memory[i+4] = pattern_1;
            memory[i+5] = pattern_1;
            memory[i+6] = pattern_1;
            memory[i+7] = pattern_1;
        }

        // Pass 2: Aggressive unrolled READ, then overwrite with Pattern 2
        for (size_t i = 0; i < num_elements; i += 8) {
            if (stop_flag.load(std::memory_order_relaxed)) return;
            
            // Volatile read forces the CPU to actually fetch from physical RAM.
            // If the RAM is unstable, this fetch will trigger hardware-level faults 
            // (like Machine Check Exceptions or silent data corruption).
            volatile uint64_t sink = memory[i] + memory[i+3] + memory[i+7];
            (void)sink;

            memory[i]   = pattern_2;
            memory[i+1] = pattern_2;
            memory[i+2] = pattern_2;
            memory[i+3] = pattern_2;
            memory[i+4] = pattern_2;
            memory[i+5] = pattern_2;
            memory[i+6] = pattern_2;
            memory[i+7] = pattern_2;
        }
    }
}

} // namespace

void run_ram_stress(std::atomic<bool>& stop_flag) {
    const size_t target_bytes = static_cast<size_t>(
        static_cast<double>(get_available_ram_bytes()) * TARGET_FRACTION
    );
    if (target_bytes == 0) return;

    // Allocate using uint64_t for optimal 64-bit alignment and maximum memory bandwidth
    std::vector<std::vector<uint64_t>> blocks;
    size_t allocated = 0;

    // Step 1: Allocate memory and fault the pages into physical RAM
    while (allocated < target_bytes && !stop_flag.load(std::memory_order_relaxed)) {
        size_t bytes_to_alloc = (target_bytes - allocated) > CHUNK_SIZE
            ? CHUNK_SIZE
            : (target_bytes - allocated);
        size_t elements_to_alloc = bytes_to_alloc / sizeof(uint64_t);

        try {
            blocks.emplace_back(elements_to_alloc, 0);
            uint64_t* data = blocks.back().data();
            
            // Touch one variable per 4096-byte page to force the OS to map it physically
            for (size_t i = 0; i < elements_to_alloc; i += 512) { 
                data[i] = 0; 
            }
            allocated += bytes_to_alloc;
        } catch (const std::bad_alloc&) {
            break; // Stop allocating if we hit a hard OS limit early
        }
    }

    // Step 2: Spin up threads to hammer the allocated blocks simultaneously
    unsigned int n_threads = std::thread::hardware_concurrency();
    if (n_threads == 0) n_threads = 1;
    
    std::vector<std::thread> workers;
    workers.reserve(n_threads);

    // Distribute the memory blocks evenly across all CPU threads
    for (unsigned int t = 0; t < n_threads; ++t) {
        workers.emplace_back([&, t]() {
            for (size_t i = t; i < blocks.size(); i += n_threads) {
                hammer_memory_chunk(blocks[i].data(), blocks[i].size(), stop_flag);
                if (stop_flag.load(std::memory_order_relaxed)) break;
            }
        });
    }

    // Wait for the user to signal a stop
    for (auto& w : workers) {
        if (w.joinable()) w.join();
    }
}

} // namespace stress
