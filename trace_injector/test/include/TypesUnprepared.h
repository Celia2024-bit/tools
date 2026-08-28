#ifndef TRACE_INJECTOR_TEST_TYPES_UNPREPARED_H
#define TRACE_INJECTOR_TEST_TYPES_UNPREPARED_H

//
// The same file with Side left unprepared, so the generator rejects it. This is
// what an aborted run is tested against: injecting validate_params() calls here
// would produce code that cannot compile, so the run has to stop before it
// modifies a single .cpp.
//
#include "CheckTraits.h"

struct Quote
{
    double price;

    bool isValid() const
    {
        return price > 0.0;
    }
};

// No check_traits<Side> anywhere. Nothing else in the file makes up for it.
enum class Side
{
    BUY,
    SELL
};

#endif // TRACE_INJECTOR_TEST_TYPES_UNPREPARED_H
