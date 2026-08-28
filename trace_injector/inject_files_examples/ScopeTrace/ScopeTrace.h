#ifndef SCOPE_TRACE_H
#define SCOPE_TRACE_H

//
// RAII entry/exit tracing, written to be injected by tools/trace_injector:
//
//     void AlphaStrategy::Run()
//     {
//         ScopeTrace trace(__FILE__, __LINE__, "AlphaStrategy::Run");
//         ...
//     }
//
// The exit line comes from the destructor rather than from a statement at the
// bottom of the body, because a function may return from anywhere and an
// injected tool cannot find every one of those places. The same destructor is
// what makes the elapsed time free: the guard already knows when it was built.
//
// The name is passed in as a literal instead of being taken from __FUNCTION__,
// which gives the bare method name — two classes with a Run() are then
// indistinguishable in the log, which is exactly the case worth tracing.
//

#include <chrono>
#include <cstdint>
#include <exception>
#include <string>

#include "Logger.h"

//
// Set to 0 and every guard compiles to nothing. That is what lets injected
// tracing stay in the source: turning it off is a build flag, not a pass of
// the remover over the whole tree.
//
#ifndef SCOPE_TRACE_ENABLED
#define SCOPE_TRACE_ENABLED 1
#endif

//
// CustomerLogLevel::DEBUG, which is 5 in src/Types.h. Written as a number so
// this header needs to know nothing about the project's own types; a tree with
// a different level map defines it on the command line.
//
#ifndef SCOPE_TRACE_LEVEL
#define SCOPE_TRACE_LEVEL 5
#endif

//
// Two spaces per level of nesting. Injected everywhere, a flat log is a wall
// of names with no call tree in it.
//
#ifndef SCOPE_TRACE_INDENT
#define SCOPE_TRACE_INDENT 2
#endif

class ScopeTrace
{
public:
    ScopeTrace(
        const char* file,
        int line,
        const char* func,
        uint8_t level = SCOPE_TRACE_LEVEL
    );

    ~ScopeTrace();

    //
    // Copying a guard would log its exit twice, and a guard that outlives its
    // scope has nothing left to measure, so neither is allowed.
    //
    ScopeTrace(const ScopeTrace&) = delete;
    ScopeTrace& operator=(const ScopeTrace&) = delete;

#if SCOPE_TRACE_ENABLED

private:
    static std::string indent();

    const char* file_;
    int line_;
    const char* func_;
    uint8_t level_;
    int exceptions_;
    std::chrono::steady_clock::time_point start_;

    //
    // Per thread. A counter shared across threads would indent one thread's
    // calls by another's depth and the tree would be nonsense.
    //
    inline static thread_local int depth_ = 0;

#endif
};

#if SCOPE_TRACE_ENABLED

inline std::string ScopeTrace::indent()
{
    return std::string(
        static_cast<std::string::size_type>(depth_ * SCOPE_TRACE_INDENT),
        ' '
    );
}

inline ScopeTrace::ScopeTrace(
    const char* file,
    int line,
    const char* func,
    uint8_t level
)
    : file_(file),
      line_(line),
      func_(func),
      level_(level),
      exceptions_(std::uncaught_exceptions()),
      start_(std::chrono::steady_clock::now())
{
    //
    // LogStream rather than the LOG macro: the macro would report this
    // header's own file and line, and the whole point of taking them as
    // arguments is to name the traced function's.
    //
    LogStream(level_, file_, func_, line_)
        << indent()
        << "-> "
        << func_;

    ++depth_;
}

inline ScopeTrace::~ScopeTrace()
{
    --depth_;

    const auto elapsed = std::chrono::duration_cast<
        std::chrono::microseconds
    >(
        std::chrono::steady_clock::now() - start_
    ).count();

    //
    // More exceptions in flight than there were on the way in means this scope
    // is being unwound, not returned from. It is the one exit no amount of
    // reading the function body reveals.
    //
    const bool unwinding = std::uncaught_exceptions() > exceptions_;

    LogStream(level_, file_, func_, line_)
        << indent()
        << "<- "
        << func_
        << " ("
        << elapsed
        << " us)"
        << (unwinding ? " [exception]" : "");
}

#else

//
// Every argument taken and dropped. The guard has no members, so an injected
// line costs a name in the source and nothing at run time.
//
inline ScopeTrace::ScopeTrace(
    const char* file,
    int line,
    const char* func,
    uint8_t level
)
{
    (void)file;
    (void)line;
    (void)func;
    (void)level;
}

inline ScopeTrace::~ScopeTrace()
{
}

#endif

#endif // SCOPE_TRACE_H
