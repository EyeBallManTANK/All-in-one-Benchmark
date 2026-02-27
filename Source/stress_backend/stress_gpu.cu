/**
 * GPU compute stress and VRAM stress using CUDA.
 * Compile with nvcc and link into the main executable when CUDA is available.
 */
 #include <cuda_runtime.h>
 #include <atomic>
 #include <chrono>
 #include <thread>
 #include <vector>
 #include <utility>
 #include <cstddef>
 #include <cstdio>
 
 #ifdef __cplusplus
 extern "C" {
 #endif
 
 // Returns 1 if CUDA device 0 is available (NVIDIA GPU present), 0 otherwise.
 int cuda_available(void);
 
 // Runs GPU compute stress (sustained high GPU utilization) until stop_flag is set.
 void run_gpu_stress(std::atomic<bool>* stop_flag);
 
 // Allocates and holds VRAM up to ~85% of free device memory until stop_flag is set.
 void run_vram_stress(std::atomic<bool>* stop_flag);
 
 #ifdef __cplusplus
 }
 #endif
 
 namespace {
 
 // -------------------------------------------------------------------------
 // GPU Compute Torture Kernel
 // -------------------------------------------------------------------------
 __global__ void gpu_stress_kernel(float* __restrict__ out) {
     // 8 independent accumulators to perfectly saturate the FP32 ALUs.
     // This allows the warp scheduler to keep the CUDA cores at 100% capacity
     // without stalling on instruction dependencies.
     float f1 = 1.1f, f2 = 1.2f, f3 = 1.3f, f4 = 1.4f;
     float f5 = 1.5f, f6 = 1.6f, f7 = 1.7f, f8 = 1.8f;
 
     // A tight, unrolled loop using Fused Multiply-Add (FMA).
     // FMA does a multiply and an add in a single clock cycle at the hardware level.
     #pragma unroll
     for (int iter = 0; iter < 4096; ++iter) {
         f1 = __fmaf_rn(f1, 1.0000001f, 0.0000001f);
         f2 = __fmaf_rn(f2, 1.0000002f, 0.0000002f);
         f3 = __fmaf_rn(f3, 1.0000003f, 0.0000003f);
         f4 = __fmaf_rn(f4, 1.0000004f, 0.0000004f);
         f5 = __fmaf_rn(f5, 1.0000005f, 0.0000005f);
         f6 = __fmaf_rn(f6, 1.0000006f, 0.0000006f);
         f7 = __fmaf_rn(f7, 1.0000007f, 0.0000007f);
         f8 = __fmaf_rn(f8, 1.0000008f, 0.0000008f);
     }
 
     // Reset before hitting infinity to keep math hardware active
     if (f1 > 1e10f) {
         f1 = 1.1f; f2 = 1.2f; f3 = 1.3f; f4 = 1.4f;
         f5 = 1.5f; f6 = 1.6f; f7 = 1.7f; f8 = 1.8f;
     }
 
     // Write-out prevents the compiler from optimizing the math away
     int idx = blockIdx.x * blockDim.x + threadIdx.x;
     out[idx] = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8;
 }
 
 // -------------------------------------------------------------------------
 // VRAM Controller Torture Kernel
 // -------------------------------------------------------------------------
 __global__ void vram_stress_kernel(unsigned long long* __restrict__ mem, size_t num_elements, unsigned long long pattern) {
     size_t idx = blockIdx.x * blockDim.x + threadIdx.x;
     size_t stride = blockDim.x * gridDim.x;
 
     // Grid-stride loop allows us to efficiently cover large VRAM chunks 
     // even with a relatively small number of threads.
     for (size_t i = idx; i < num_elements; i += stride) {
         mem[i] = pattern;
         
         // Volatile read-back forces the data to travel both ways across the VRAM bus
         volatile unsigned long long sink = mem[i];
         (void)sink;
     }
 }
 
 
 void run_gpu_stress_impl(std::atomic<bool>* stop_flag) {
     cudaError_t err = cudaSetDevice(0);
     if (err != cudaSuccess) {
         std::fprintf(stderr, "CUDA cudaSetDevice(0) failed: %s\n", cudaGetErrorString(err));
         return;
     }
 
     // Query the GPU to find out exactly how many Streaming Multiprocessors (SMs) it has.
     int num_sm = 0;
     cudaDeviceGetAttribute(&num_sm, cudaDevAttrMultiProcessorCount, 0);
     if (num_sm == 0) num_sm = 68; // Fallback (e.g., RTX 3080 size)
 
     // Tailor the grid size to perfectly fill the GPU without overloading the queue.
     // This ensures execution happens in fast <50ms chunks, preventing OS freezes (TDR).
     const int block = 256;
     const int grid = num_sm * 32; 
     const size_t out_bytes = static_cast<size_t>(grid * block) * sizeof(float);
 
     float* d_out = nullptr;
     err = cudaMalloc(&d_out, out_bytes);
     if (err != cudaSuccess) return;
 
     while (stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
         gpu_stress_kernel<<<grid, block>>>(d_out);
         
         // Synchronize allows the OS to draw frames to the screen between launches
         err = cudaDeviceSynchronize();
         if (err != cudaSuccess) break;
     }
 
     if (d_out) cudaFree(d_out);
 }
 
 void run_vram_stress_impl(std::atomic<bool>* stop_flag) {
     cudaError_t err = cudaSetDevice(0);
     if (err != cudaSuccess) {
         std::fprintf(stderr, "CUDA cudaSetDevice(0) failed: %s\n", cudaGetErrorString(err));
         return;
     }
 
     size_t free_mem = 0, total_mem = 0;
     err = cudaMemGetInfo(&free_mem, &total_mem);
     if (err != cudaSuccess) return;
 
     // Dropped from 95% to 85%. Modern OS desktop compositors need breathing room.
     // If you starve the WDDM/X11 compositor entirely, the OS GUI will crash.
     const size_t target = static_cast<size_t>(static_cast<double>(free_mem) * 0.85);
     const size_t chunk_bytes = 64 * 1024 * 1024;  // 64 MiB
     const size_t chunk_elements = chunk_bytes / sizeof(unsigned long long);
 
     std::vector<std::pair<unsigned long long*, size_t>> blocks;
     size_t allocated = 0;
 
     while (allocated < target && stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
         size_t to_alloc_bytes = (target - allocated) > chunk_bytes ? chunk_bytes : (target - allocated);
         unsigned long long* p = nullptr;
         err = cudaMalloc((void**)&p, to_alloc_bytes);
         if (err != cudaSuccess) break; // Stop allocating if fragmentation blocks us
         
         blocks.emplace_back(p, to_alloc_bytes / sizeof(unsigned long long));
         allocated += to_alloc_bytes;
     }
 
     // Alternate bits to generate maximum electrical stress on the memory controller
     const unsigned long long pattern_1 = 0x5555555555555555ULL;
     const unsigned long long pattern_2 = 0xAAAAAAAAAAAAAAAAULL;
     bool toggle = false;
 
     // Calculate generic grid/block for the VRAM copy
     int num_sm = 0;
     cudaDeviceGetAttribute(&num_sm, cudaDevAttrMultiProcessorCount, 0);
     if (num_sm == 0) num_sm = 68;
     const int block = 256;
     const int grid = num_sm * 16; 
 
     while (stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
         unsigned long long current_pattern = toggle ? pattern_1 : pattern_2;
         toggle = !toggle;
 
         for (const auto& pr : blocks) {
             vram_stress_kernel<<<grid, block>>>(pr.first, pr.second, current_pattern);
             
             if (stop_flag->load(std::memory_order_relaxed)) break;
         }
         
         // Syncing after a full pass allows the system to remain responsive
         cudaDeviceSynchronize();
     }
 
     for (const auto& pr : blocks) {
         cudaFree(pr.first);
     }
 }
 
 } // namespace
 
 #ifdef __cplusplus
 extern "C" {
 #endif
 
 int cuda_available(void) {
     return (cudaSetDevice(0) == cudaSuccess) ? 1 : 0;
 }
 
 void run_gpu_stress(std::atomic<bool>* stop_flag) {
     run_gpu_stress_impl(stop_flag);
 }
 
 void run_vram_stress(std::atomic<bool>* stop_flag) {
     run_vram_stress_impl(stop_flag);
 }
 
 #ifdef __cplusplus
 }
 #endif