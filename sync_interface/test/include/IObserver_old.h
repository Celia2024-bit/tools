#pragma once

class IObserver
{
public:

    virtual ~IObserver() = default;

    virtual void OnConnected() = 0;

    virtual void OnData(int id) = 0;
};