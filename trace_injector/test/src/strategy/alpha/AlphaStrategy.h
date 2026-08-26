#pragma once

#include "../StrategyEngine.h"

class AlphaStrategy : public StrategyEngine
{
public:

    void Run() override;

    void Evaluate();

    void Rebalance();
};
