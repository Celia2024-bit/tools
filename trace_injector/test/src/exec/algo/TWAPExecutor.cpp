// src/exec/algo/TWAPExecutor.cpp
#include "TWAPExecutor.h"
#include <iostream>

namespace exec {
namespace algo {

bool TWAPExecutor::Execute(const std::string& order_id, double quantity)
{
    return Execute(order_id, quantity, 300); // 默认 300 秒窗口
}

bool TWAPExecutor::Execute(const std::string& order_id, double quantity, int time_window_sec)
{
    std::cout << "[TWAP] Executing order " << order_id 
              << " over " << time_window_sec << " seconds." << std::endl;
    return true;
}

} // namespace algo
} // namespace exec