// LoggerObserver.h

#pragma once

#include "IObserver.h"

class LoggerObserver : public IObserver
{
public:

    void OnConnected() override;
    void OnData(int id) override;
};