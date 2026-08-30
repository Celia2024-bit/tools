#pragma once
#include <string>

namespace exec {

class IExecutor {
public:
    virtual ~IExecutor() = default;
    virtual bool Execute(const std::string& order_id, double quantity) = 0;
};

class OrderExecutor : public IExecutor {
public:
    bool Execute(const std::string& order_id, double quantity) override;
};

} // namespace exec