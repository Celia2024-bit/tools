// src/exec/BatchExecutor.cpp
#include "BatchExecutor.h"
#include <iostream>

namespace exec {

bool BatchExecutor::Execute(const std::string& order_id, double quantity)
{
    std::cout << "[BATCH] Batch item: " << order_id << std::endl;
    return true;
}

void BatchExecutor::LogStatus()
{
    std::cout << "[BATCH] Status Normal" << std::endl;
}

} // namespace exec