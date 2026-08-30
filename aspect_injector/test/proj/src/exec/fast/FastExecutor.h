#pragma once

#include "../OrderExecutor.h"

class FastExecutor : public OrderExecutor
{
public:

    void Execute() override;
};
