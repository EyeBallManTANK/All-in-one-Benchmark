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

// Runs GPU compute stress (sustained high GPU utilization) until stop_flag is set.
void run_gpu_stress(std::atomic<bool>* stop_flag);

// Allocates and holds VRAM up to ~90% of free device memory until stop_flag is set.
void run_vram_stress(std::atomic<bool>* stop_flag);

#ifdef __cplusplus
}
#endif

namespace {

__global__ void gpu_stress_kernel(float* __restrict__ out, const float* __restrict__ in, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i >= n) return;
    float x = in[i];
    for (int iter = 0; iter < 8192; ++iter) {
        x = x * 1.0000001f + 0.0000001f;
        x = (x > 1e10f) ? x * 1e-10f : x;
    }
    out[i] = x;
}

void run_gpu_stress_impl(std::atomic<bool>* stop_flag) {
    cudaError_t err = cudaSetDevice(0);
    if (err != cudaSuccess) {
        std::fprintf(stderr, "CUDA cudaSetDevice(0) failed: %s\n", cudaGetErrorString(err));
        return;
    }

    const int n = 1 << 22;  // 4M floats
    const size_t bytes = static_cast<size_t>(n) * sizeof(float);

    float* d_in = nullptr;
    float* d_out = nullptr;
    err = cudaMalloc(&d_in, bytes);
    if (err != cudaSuccess) goto cleanup_gpu;
    err = cudaMalloc(&d_out, bytes);
    if (err != cudaSuccess) goto cleanup_gpu;

    const int block = 256;
    const int grid = (n + block - 1) / block;

    while (stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
        gpu_stress_kernel<<<grid, block>>>(d_out, d_in, n);
        err = cudaDeviceSynchronize();
        if (err != cudaSuccess) break;
    }

cleanup_gpu:
    if (d_in) cudaFree(d_in);
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

    const size_t target = static_cast<size_t>(static_cast<double>(free_mem) * 0.95);
    const size_t chunk = 64 * 1024 * 1024;  // 64 MiB

    std::vector<std::pair<void*, size_t>> blocks;
    size_t allocated = 0;

    while (allocated < target && stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
        size_t to_alloc = (target - allocated) > chunk ? chunk : (target - allocated);
        void* p = nullptr;
        err = cudaMalloc(&p, to_alloc);
        if (err != cudaSuccess) break;
        blocks.emplace_back(p, to_alloc);
        allocated += to_alloc;
    }

    // Continuously touch VRAM so the memory controller is actually stressed
    while (stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
        for (const auto& pr : blocks) {
            if (cudaMemset(pr.first, 0xAB, pr.second) != cudaSuccess) break;
        }
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

void run_gpu_stress(std::atomic<bool>* stop_flag) {
    run_gpu_stress_impl(stop_flag);
}

void run_vram_stress(std::atomic<bool>* stop_flag) {
    run_vram_stress_impl(stop_flag);
}

#ifdef __cplusplus
}
#endif
