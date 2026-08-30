#include "OrderProcessor.h"
#include <iostream>

namespace hot {


bool OrderProcessor::ProcessOrder(int account_id, double notional, int order_type)
{
    std::cout << "Processing order for account: " << account_id 
              << " with notional: " << notional << std::endl;
    
    return true;
}


void OrderProcessor::ResetState()
{
    std::cout << "Resetting hot processor state." << std::endl;
}

} // namespace hot