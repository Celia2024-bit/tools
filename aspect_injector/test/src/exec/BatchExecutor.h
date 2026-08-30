#pragma once
#include "OrderExecutor.h"
#include <vector>

namespace exec {

class ILoggable {
public:
    virtual ~ILoggable() = default;
    virtual void LogStatus() = 0;
};

class BatchExecutor : public IExecutor, public ILoggable {
public:
    bool Execute(const std::string& order_id, double quantity) override;
    void LogStatus() override;
};

} // namespace exec