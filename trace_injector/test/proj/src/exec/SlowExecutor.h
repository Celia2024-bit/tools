#pragma once

#include "OrderExecutor.h"

//
// Private inheritance: still an override, so base_class still matches it.
//
class SlowExecutor : private OrderExecutor
{
public:

    void Execute() override;
};
