#include "OrderExecutor.h"
#include <iostream>
#include <stdexcept>

namespace exec {

bool OrderExecutor::Execute(const std::string& order_id, double quantity)
{
    if (quantity <= 0.0) {
        throw std::invalid_argument("Execution quantity must be positive");
    }

    std::cout << "Executing order: " << order_id 
              << " with qty: " << quantity << std::endl;

    return true;
}

} // namespace exec