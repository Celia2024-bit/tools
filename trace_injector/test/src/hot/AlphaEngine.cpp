#include "AlphaEngine.h"
#include <iostream>
#include <stdexcept>

namespace hot {

void AlphaEngine::OnTick(int symbol_id, double price, double /*unnamed_volume*/)
{
    if (price <= 0.0) {
        throw std::invalid_argument("Price must be positive");
    }
    
    std::cout << "Tick received for symbol " << symbol_id << " at " << price << std::endl;
}

} // namespace hot