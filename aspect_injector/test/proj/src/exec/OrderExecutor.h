#pragma once

//
// Written against the project include root, NOT relative to this file —
// clang can only resolve it when "include_dirs" lists test/proj/include.
//
#include "framework/IExecutor.h"

class OrderExecutor : public IExecutor
{
public:

    void Execute() override;
};
