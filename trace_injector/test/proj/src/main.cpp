#include <iostream>
#include "ScopeTrace.h"  // @autogen: include for trace
#include "ErrorLogger.h"  // @autogen: include for guard

int main() {
    ScopeTrace trace(  // @autogen: trace
        __FILE__,  // @autogen: trace
        __LINE__,  // @autogen: trace
        "main"  // @autogen: trace
    );  // @autogen: trace

    try  // @autogen: guard
    {  // @autogen: guard

    std::cout << "==================================================" << std::endl;
    std::cout << "   [Test Runner] C++ Injection Verification Pass! " << std::endl;
    std::cout << "==================================================" << std::endl;
    return 0;
    }  // @autogen: end of guard
    catch (const std::exception& error)  // @autogen: end of guard
    {  // @autogen: end of guard
        ErrorLogger::LogError("", "main", "std::exception", error.what());  // @autogen: end of guard
        throw;  // @autogen: end of guard
    }  // @autogen: end of guard
    catch (...)  // @autogen: end of guard
    {  // @autogen: end of guard
        ErrorLogger::LogError("", "main", "unknown", "unrecognised exception");  // @autogen: end of guard
        throw;  // @autogen: end of guard
    }  // @autogen: end of guard
}