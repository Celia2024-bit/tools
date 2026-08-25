#pragma once

#include "IObserver.h"

class StrategyObserver : public IObserver
{
public:

    void OnConnected() override;
    void OnData(int id) override;
};
``