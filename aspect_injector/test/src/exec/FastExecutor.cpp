// src/exec/FastExecutor.cpp
#include "FastExecutor.h"
#include <iostream>

namespace exec {

bool FastExecutor::Execute(const std::string& order_id, double quantity)
{
    std::cout << "[FAST PATH] Executing order: " << order_id 
              << " with qty: " << quantity << std::endl;
    return true;
}

} // namespace exec