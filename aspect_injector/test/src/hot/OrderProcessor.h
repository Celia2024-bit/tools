#pragma once

namespace hot {

class OrderProcessor {
public:
    OrderProcessor() = default;
    ~OrderProcessor() = default;

    bool ProcessOrder(int account_id, double notional, int order_type);

    void ResetState();
};

} // namespace hot