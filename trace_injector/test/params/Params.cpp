#include "Params.h"

void Params::Three(
    int count,
    double price,
    const char* symbol
)
{
    (void)count;
}

void Params::Unnamed(int)
{
}

void Params::Nothing()
{
}

void Params::Variadic(
    const char* format,
    ...
)
{
    (void)format;
}
