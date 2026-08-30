#pragma once

//
// Free functions: no owning class, so labels stay unqualified except for
// the enclosing namespace.
//
namespace util
{
    void Reset();
}

double Normalize(
    double value
);
