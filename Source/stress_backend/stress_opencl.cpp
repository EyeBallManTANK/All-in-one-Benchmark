/**
 * GPU compute and VRAM stress using OpenCL (AMD, Intel, and NVIDIA).
 * Used when CUDA is not available or not built.
 */
 #include <CL/cl.h>
 #include <atomic>
 #include <chrono>
 #include <cstdio>
 #include <cstring>
 #include <thread>
 #include <utility>
 #include <vector>
 
 #ifdef __cplusplus
 extern "C" {
 #endif
 
 void run_gpu_stress_opencl(std::atomic<bool>* stop_flag);
 void run_vram_stress_opencl(std::atomic<bool>* stop_flag);
 
 #ifdef __cplusplus
 }
 #endif
 
 namespace {
 
 // -------------------------------------------------------------------------
 // GPU Compute Torture Kernel
 // -------------------------------------------------------------------------
 const char* gpu_stress_src = R"(
 __kernel void stress(__global float* out) {
     // 8 independent accumulators to perfectly saturate superscalar ALUs across 
     // AMD, Intel, and NVIDIA architectures without instruction stalling.
     float f1 = 1.1f, f2 = 1.2f, f3 = 1.3f, f4 = 1.4f;
     float f5 = 1.5f, f6 = 1.6f, f7 = 1.7f, f8 = 1.8f;
 
     // fma() is the OpenCL standard built-in for hardware Fused Multiply-Add
     for (int iter = 0; iter < 4096; ++iter) {
         f1 = fma(f1, 1.0000001f, 0.0000001f);
         f2 = fma(f2, 1.0000002f, 0.0000002f);
         f3 = fma(f3, 1.0000003f, 0.0000003f);
         f4 = fma(f4, 1.0000004f, 0.0000004f);
         f5 = fma(f5, 1.0000005f, 0.0000005f);
         f6 = fma(f6, 1.0000006f, 0.0000006f);
         f7 = fma(f7, 1.0000007f, 0.0000007f);
         f8 = fma(f8, 1.0000008f, 0.0000008f);
     }
 
     if (f1 > 1e10f) {
         f1 = 1.1f; f2 = 1.2f; f3 = 1.3f; f4 = 1.4f;
         f5 = 1.5f; f6 = 1.6f; f7 = 1.7f; f8 = 1.8f;
     }
 
     int i = get_global_id(0);
     out[i] = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8;
 }
 )";
 
 // -------------------------------------------------------------------------
 // VRAM Controller Torture Kernel
 // -------------------------------------------------------------------------
 const char* vram_stress_src = R"(
 __kernel void vram_stress(__global ulong* mem, const ulong pattern) {
     size_t i = get_global_id(0);
     
     // Write the aggressive bit pattern to memory
     mem[i] = pattern;
     
     // Volatile read-back forces the data to travel back across the VRAM bus,
     // maximizing electrical draw and exposing faulty traces/chips.
     volatile ulong sink = mem[i];
 }
 )";
 
 void run_gpu_stress_opencl_impl(std::atomic<bool>* stop_flag) {
     cl_platform_id platform = nullptr;
     cl_device_id device = nullptr;
     cl_int err = clGetPlatformIDs(1, &platform, nullptr);
     if (err != CL_SUCCESS || !platform) return;
 
     err = clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 1, &device, nullptr);
     if (err != CL_SUCCESS || !device) return;
 
     cl_context ctx = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &err);
     if (err != CL_SUCCESS || !ctx) return;
 
     cl_command_queue queue = clCreateCommandQueue(ctx, device, 0, &err);
     if (err != CL_SUCCESS || !queue) {
         clReleaseContext(ctx);
         return;
     }
 
     cl_program prog = clCreateProgramWithSource(ctx, 1, &gpu_stress_src, nullptr, &err);
     if (err == CL_SUCCESS) err = clBuildProgram(prog, 1, &device, nullptr, nullptr, nullptr);
     
     cl_kernel kernel = nullptr;
     if (err == CL_SUCCESS) kernel = clCreateKernel(prog, "stress", &err);
 
     if (err != CL_SUCCESS || !kernel) {
         if (prog) clReleaseProgram(prog);
         clReleaseCommandQueue(queue);
         clReleaseContext(ctx);
         return;
     }
 
     // Query compute units to scale the grid size dynamically.
     // This perfectly saturates the GPU while keeping execution times short enough to prevent OS freezes.
     cl_uint compute_units = 0;
     clGetDeviceInfo(device, CL_DEVICE_MAX_COMPUTE_UNITS, sizeof(compute_units), &compute_units, nullptr);
     if (compute_units == 0) compute_units = 32;
 
     const size_t local = 256;
     const size_t global = compute_units * local * 32; // Scale workload to the hardware
     const size_t bytes = global * sizeof(cl_float);
 
     cl_mem d_out = clCreateBuffer(ctx, CL_MEM_WRITE_ONLY, bytes, nullptr, &err);
     if (err == CL_SUCCESS) {
         clSetKernelArg(kernel, 0, sizeof(cl_mem), &d_out);
 
         while (stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
             err = clEnqueueNDRangeKernel(queue, kernel, 1, nullptr, &global, &local, 0, nullptr, nullptr);
             if (err != CL_SUCCESS) break;
             
             // Sync ensures the OS compositor can draw the desktop screen
             clFinish(queue); 
         }
         clReleaseMemObject(d_out);
     }
 
     clReleaseKernel(kernel);
     clReleaseProgram(prog);
     clReleaseCommandQueue(queue);
     clReleaseContext(ctx);
 }
 
 void run_vram_stress_opencl_impl(std::atomic<bool>* stop_flag) {
     cl_platform_id platform = nullptr;
     cl_device_id device = nullptr;
     cl_int err = clGetPlatformIDs(1, &platform, nullptr);
     if (err != CL_SUCCESS || !platform) return;
 
     err = clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 1, &device, nullptr);
     if (err != CL_SUCCESS || !device) return;
 
     cl_ulong global_mem = 0;
     clGetDeviceInfo(device, CL_DEVICE_GLOBAL_MEM_SIZE, sizeof(global_mem), &global_mem, nullptr);
     if (err != CL_SUCCESS || global_mem == 0) return;
 
     cl_context ctx = clCreateContext(nullptr, 1, &device, nullptr, nullptr, &err);
     if (err != CL_SUCCESS || !ctx) return;
 
     cl_command_queue queue = clCreateCommandQueue(ctx, device, 0, &err);
     if (err != CL_SUCCESS || !queue) {
         clReleaseContext(ctx);
         return;
     }
 
     cl_program prog = clCreateProgramWithSource(ctx, 1, &vram_stress_src, nullptr, &err);
     if (err == CL_SUCCESS) err = clBuildProgram(prog, 1, &device, nullptr, nullptr, nullptr);
     
     cl_kernel kernel = nullptr;
     if (err == CL_SUCCESS) kernel = clCreateKernel(prog, "vram_stress", &err);
 
     if (err != CL_SUCCESS || !kernel) {
         if (prog) clReleaseProgram(prog);
         clReleaseCommandQueue(queue);
         clReleaseContext(ctx);
         return;
     }
 
     // Target 85% of total VRAM. OpenCL doesn't have an easy "get free memory" query like CUDA,
     // so we cap out at 85% and rely on buffer allocation failures to stop us if the OS is using too much.
     size_t target = static_cast<size_t>(static_cast<double>(global_mem) * 0.85);
     const size_t chunk = 64 * 1024 * 1024; // 64 MiB
     
     std::vector<std::pair<cl_mem, size_t>> buffers;
     size_t allocated = 0;
 
     // Allocate chunks of VRAM
     while (allocated < target && stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
         size_t to_alloc = (target - allocated) > chunk ? chunk : (target - allocated);
         cl_mem buf = clCreateBuffer(ctx, CL_MEM_READ_WRITE, to_alloc, nullptr, &err);
         if (err != CL_SUCCESS) break; // Break out if we hit OS limits or fragmentation
         
         buffers.emplace_back(buf, to_alloc);
         allocated += to_alloc;
     }
 
     const cl_ulong pattern_1 = 0x5555555555555555ULL;
     const cl_ulong pattern_2 = 0xAAAAAAAAAAAAAAAAULL;
     bool toggle = false;
     const size_t local = 256;
 
     while (stop_flag && !stop_flag->load(std::memory_order_relaxed)) {
         cl_ulong current_pattern = toggle ? pattern_1 : pattern_2;
         toggle = !toggle;
 
         for (const auto& p : buffers) {
             size_t num_elements = p.second / sizeof(cl_ulong);
             // Global size must be a multiple of local size for optimal OpenCL dispatch
             size_t global = ((num_elements + local - 1) / local) * local; 
 
             clSetKernelArg(kernel, 0, sizeof(cl_mem), &p.first);
             clSetKernelArg(kernel, 1, sizeof(cl_ulong), &current_pattern);
 
             err = clEnqueueNDRangeKernel(queue, kernel, 1, nullptr, &global, &local, 0, nullptr, nullptr);
             if (err != CL_SUCCESS) break;
         }
         clFinish(queue); // Keep system responsive
     }
 
     for (const auto& p : buffers) clReleaseMemObject(p.first);
     clReleaseKernel(kernel);
     clReleaseProgram(prog);
     clReleaseCommandQueue(queue);
     clReleaseContext(ctx);
 }
 
 }  // namespace
 
 #ifdef __cplusplus
 extern "C" {
 #endif
 
 void run_gpu_stress_opencl(std::atomic<bool>* stop_flag) {
     run_gpu_stress_opencl_impl(stop_flag);
 }
 
 void run_vram_stress_opencl(std::atomic<bool>* stop_flag) {
     run_vram_stress_opencl_impl(stop_flag);
 }
 
 #ifdef __cplusplus
 }
 #endif