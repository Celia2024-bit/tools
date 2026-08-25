#pragma once

#include "IObserver.h"

class AlphaObserver : public IObserver
{
public:

    void OnConnected() override;
    void OnData(int id) override;
};