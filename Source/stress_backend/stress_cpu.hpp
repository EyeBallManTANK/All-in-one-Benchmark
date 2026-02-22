#pragma once

#include <atomic>
#include <cstddef>

namespace stress {

// Runs CPU stress on all logical cores until stop_flag becomes true.
// Uses one thread per logical core doing busy work for accurate load.
void run_cpu_stress(std::atomic<bool>& stop_flag);

} // namespace stress
