// MarketObserver.cpp

#include "MarketObserver.h"

#include <cstdio>

void MarketObserver::OnConnected()
{
    std::printf("[MarketObserver] Connected\n");
}

void MarketObserver::OnData(int id)
{
    std::printf("[MarketObserver] Data received, id=%d\n", id);
}
