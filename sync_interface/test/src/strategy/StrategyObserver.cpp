// StrategyObserver.cpp

#include "StrategyObserver.h"

#include <cstdio>

void StrategyObserver::OnConnected()
{
    std::printf("[StrategyObserver] Connected\n");
}

void StrategyObserver::OnData(int id)
{
    std::printf("[StrategyObserver] Data received, id=%d\n", id);
}
