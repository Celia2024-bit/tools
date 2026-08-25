#pragma once

#include "IObserver.h"

class MarketObserver : public IObserver
{
public:

    void OnConnected() override;
    void OnData(int id) override;
};