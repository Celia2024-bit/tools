#ifndef TRACE_INJECTOR_TEST_TYPES_H
#define TRACE_INJECTOR_TEST_TYPES_H

//
// A Types.h the ParameterCheck generator accepts, so a "validate" rule can be
// tested end to end. Deliberately minimal: the point here is the generator's
// verdict, not the type system — parameters_check has its own fixtures for
// that.
//
// CheckTraits.h is not checked in beside this file. The generator deposits it
// here as part of generating ParameterCheck.h, which is the arrangement a real
// project ends up with.
//
#include "CheckTraits.h"

struct Quote
{
    double price;

    // Prepared by having a check of its own.
    bool isValid() const
    {
        return price > 0.0;
    }
};

enum class Side
{
    BUY,
    SELL
};

// An enum cannot carry isValid(), so it is prepared from the outside.
template<>
struct check_traits<Side>
{
    static bool check(const Side& side)
    {
        return side == Side::BUY || side == Side::SELL;
    }
};

#endif // TRACE_INJECTOR_TEST_TYPES_H
