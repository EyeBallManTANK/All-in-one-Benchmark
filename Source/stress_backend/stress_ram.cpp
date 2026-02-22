#include "stress_ram.hpp"
#include <thread>
#include <chrono>
#include <cstring>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

namespace stress {

namespace {

constexpr double TARGET_FRACTION = 0.95;  // Use up to 95% of available RAM
constexpr size_t CHUNK_SIZE = 64 * 1024 * 1024;  // 64 MiB per chunk (touch in chunks)

#ifdef _WIN32
size_t get_available_ram_bytes() {
    MEMORYSTATUSEX ms = {};
    ms.dwLength = sizeof(ms);
    if (!GlobalMemoryStatusEx(&ms)) return 0;
    return static_cast<size_t>(ms.ullAvailPhys);
}
#else
#include <sys/sysinfo.h>
size_t get_available_ram_bytes() {
    struct sysinfo si = {};
    if (sysinfo(&si) != 0) return 0;
    return static_cast<size_t>(si.freeram) * si.mem_unit;
}
#endif

void touch_memory(char* base, size_t size) {
    const size_t page = 4096;
    for (size_t i = 0; i < size; i += page) {
        base[i] = static_cast<char>(i & 0xFF);
    }
}

} // namespace

void run_ram_stress(std::atomic<bool>& stop_flag) {
    const size_t target_bytes = static_cast<size_t>(
        static_cast<double>(get_available_ram_bytes()) * TARGET_FRACTION
    );
    if (target_bytes == 0) return;

    std::vector<std::vector<char>> blocks;
    size_t allocated = 0;

    while (allocated < target_bytes && !stop_flag.load(std::memory_order_relaxed)) {
        size_t to_alloc = (target_bytes - allocated) > CHUNK_SIZE
            ? CHUNK_SIZE
            : (target_bytes - allocated);
        try {
            blocks.emplace_back(to_alloc, 0);
            touch_memory(blocks.back().data(), to_alloc);
            allocated += to_alloc;
        } catch (const std::bad_alloc&) {
            break;
        }
    }

    // Keep allocated and continuously read/write to stress memory bandwidth
    while (!stop_flag.load(std::memory_order_relaxed)) {
        for (auto& block : blocks) {
            touch_memory(block.data(), block.size());
        }
    }
}

} // namespace stress
