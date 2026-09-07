// AlphaObserver.cpp

#include "AlphaObserver.h"

#include <cstdio>

void AlphaObserver::OnConnected()
{
    std::printf("[AlphaObserver] Connected\n");
}

void AlphaObserver::OnData(int id)
{
    std::printf("[AlphaObserver] Data received, id=%d\n", id);
}

void AlphaObserver::OnData(int id, double timestamp)
{
    // TODO: implement
}

void AlphaObserver::OnError(int err_code)
{
    // TODO: implement
}

