#pragma once
#include "OrderExecutor.h"

namespace exec {

class FastExecutor : public OrderExecutor {
public:
    bool Execute(const std::string& order_id, double quantity) override;
};

} // namespace exec