#pragma once
#include "../OrderExecutor.h"

namespace exec {
namespace algo {

class TWAPExecutor : public IExecutor {
public:
    // 1. 实现基类虚函数（匹配规则）
    bool Execute(const std::string& order_id, double quantity) override;

    // 2. 同名重载函数（增加算法参数，同样会被 function: "Execute" + base_class 匹配到）
    bool Execute(const std::string& order_id, double quantity, int time_window_sec);
};

} // namespace algo
} // namespace exec