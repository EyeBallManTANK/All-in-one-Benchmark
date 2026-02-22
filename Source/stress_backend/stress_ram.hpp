#pragma once

#include <atomic>
#include <cstddef>
#include <vector>

namespace stress {

// Targets ~90% of available physical RAM; touches pages so they're committed.
// Runs until stop_flag becomes true (keeps memory allocated).
void run_ram_stress(std::atomic<bool>& stop_flag);

} // namespace stress
