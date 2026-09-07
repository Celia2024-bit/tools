// LoggerObserver.cpp

#include "LoggerObserver.h"

#include <cstdio>

void LoggerObserver::OnConnected()
{
    std::printf("[LoggerObserver] Connected\n");
}

void LoggerObserver::OnData(int id)
{
    std::printf("[LoggerObserver] Data received, id=%d\n", id);
}

void LoggerObserver::OnData(int id, double timestamp)
{
    // TODO: implement
}

void LoggerObserver::OnError(int err_code)
{
    // TODO: implement
}

