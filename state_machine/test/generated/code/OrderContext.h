#ifndef ORDER_CONTEXT_H
#define ORDER_CONTEXT_H

#include <string>
#include <vector>

struct OrderContext {
    int orderId;
    double amount;
    std::string reason;
};

#endif // ORDER_CONTEXT_H