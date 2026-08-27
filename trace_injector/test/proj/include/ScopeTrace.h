#pragma once

//
// A stand-in, not the real thing: the fixtures only need this to exist and to
// parse, so that a file the injector has already touched still parses on the
// next run. Injecting the #include is what makes that matter.
//
class ScopeTrace
{
public:

    ScopeTrace(
        const char* file,
        int line,
        const char* func)
    {
        (void)file;
        (void)line;
        (void)func;
    }

    ~ScopeTrace()
    {
    }
};
