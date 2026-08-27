#include "Legacy.h"

//
// Trace-free at rest, like every other fixture. The scenarios that need a
// trace already in place write their own version of this file through
// `setup_files`, and the snapshot puts this one back afterwards.
//
void Legacy::Old()
{
    int a = 1;
}

void Legacy::New()
{
    int b = 2;
}
