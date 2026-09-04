#pragma once

#include "IObserver.h"

class NetworkObserver : public IObserver
{
public:

    void OnConnected();
    void OnData(int id);
    void OnData(int id, double timestamp);
    void OnError(int err_code) override;
    void OnData(int id, double timestamp) override;
    void OnError(int err_code) override;
};