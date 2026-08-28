# Inject files

The headers the injected code refers to. `trace_injector` writes calls, never
includes (see "Known limitations" in `../README.md`), so getting these in front
of the compiler is the project's job, not the tool's.

| File | Provides | Needs |
|---|---|---|
| `ScopeTrace/ScopeTrace.h` | the `ScopeTrace` guard that `inject_type: ["trace"]` writes | `Logger.h` — the project's own, i.e. `TradeSystem/util/Logger.h` |

`ParameterCheck.h` is deliberately absent: it is **generated** against one
specific `Types.h`, so a copy checked in here would be a header built for
somebody else's types. The `headers` block in the config is how you get it —
`../README.md` covers that.

## ScopeTrace.h

Header only, and `#include "Logger.h"` is its only dependency — specifically a
`LogStream(uint8_t level, const char* file, const char* func, int line)`, which
is what lets a guard report the *traced* function's file and line instead of
this header's. `TradeSystem/util/Logger.h` has exactly that constructor. A
project whose logger does not is the one place this file needs editing.

Three build flags, all defaulted, none required:

| Macro | Default | Effect |
|---|---|---|
| `SCOPE_TRACE_ENABLED` | `1` | `0` compiles every guard to nothing, members and all |
| `SCOPE_TRACE_LEVEL` | `5` | log level of the enter/exit lines (`CustomerLogLevel::DEBUG`) |
| `SCOPE_TRACE_INDENT` | `2` | spaces of indent per level of call depth, per thread |

`SCOPE_TRACE_ENABLED=0` is why injected tracing can stay in the source: turning
it off is a compiler flag, not another pass of `remove` over the whole tree.
Both settings compile:

```
g++ -std=c++17 -fsyntax-only your.cpp
g++ -std=c++17 -DSCOPE_TRACE_ENABLED=0 -fsyntax-only your.cpp
```
