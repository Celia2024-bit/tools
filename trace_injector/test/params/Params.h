#pragma once

//
// One method per shape a parameter payload has to cope with: several named
// parameters, one with no name, none at all, and a variadic tail.
//
class Params
{
public:
    void Three(int count, double price, const char* symbol);
    void Unnamed(int);
    void Nothing();
    void Variadic(const char* format, ...);
};
