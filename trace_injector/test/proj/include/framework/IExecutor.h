#pragma once

class IExecutor
{
public:

    virtual ~IExecutor() = default;

    virtual void Execute() = 0;
};
