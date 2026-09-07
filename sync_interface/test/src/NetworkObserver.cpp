// NetworkObserver.cpp

#include "NetworkObserver.h"

#include <cstdio>

void NetworkObserver::OnConnected()
{
    std::printf("[NetworkObserver] Connected\n");
}

void NetworkObserver::OnData(int id)
{
    std::printf("[NetworkObserver] Data received, id=%d\n", id);
}

void NetworkObserver::OnData(int id, double timestamp)
{
    // TODO: implement
}

void NetworkObserver::OnError(int err_code)
{
    // TODO: implement
}

