#include <iostream>
#include <vector>
#include <thread>
#include <cmath>
#include <process.h> // Windows 下获取 getpid()

void heavy_task() {
    double x = 0;
    while (true) {
        // 执行大量计算，诱发内核强制抢占时间片
        x += std::sin(std::sqrt(rand() % 1000));
    }
}

int main() {
    // 1. 获取 PID
    int pid = _getpid();
    
    // 2. 创建大量线程 (建议设置为核心数的 10 倍以上)
    int thread_count = 128; 

    std::cout << "====================================" << std::endl;
    std::cout << "🔥 C++ Involuntary Ctx Switch Simulator" << std::endl;
    std::cout << "📌 TARGET PID: " << pid << std::endl;
    std::cout << "🚀 Creating " << thread_count << " threads..." << std::endl;
    std::cout << "====================================" << std::endl;

    std::vector<std::thread> workers;
    for (int i = 0; i < thread_count; ++i) {
        workers.emplace_back(heavy_task);
    }

    std::cout << "⚡ Simulation is RUNNING. Check your monitor now!" << std::endl;

    for (auto& t : workers) {
        t.join();
    }

    return 0;
}