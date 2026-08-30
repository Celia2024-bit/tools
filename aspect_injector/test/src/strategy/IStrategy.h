#pragma once

class IStrategy
{
public:

    virtual ~IStrategy() = default;

    virtual void Run() = 0;

    virtual void Stop();
};
