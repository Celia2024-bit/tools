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
