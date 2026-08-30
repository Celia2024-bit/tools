#pragma once

#include "IStrategy.h"

class StrategyEngine : public IStrategy
{
public:

    void Run() override;

    void Stop() override;
};
