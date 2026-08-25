#pragma once

#include "IObserver.h"

class NetworkObserver : public IObserver
{
public:
    void OnConnected() override;
    void OnData(int id) override;
};