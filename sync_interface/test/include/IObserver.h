#pragma once

class IObserver
{
public:

    virtual ~IObserver() = default;

    virtual void OnData(int id, double timestamp) = 0;

    virtual void OnError(int err_code) = 0;
};
