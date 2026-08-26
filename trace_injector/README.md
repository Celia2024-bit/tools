# Trace Injector

Inserts (or strips) a `ScopeTrace` guard at the top of C++ function bodies,
driven by `config.json`. Function boundaries come from libclang's AST, not
from regex, so overloads and multi-line signatures are handled correctly.

```
python trace_injector.py --config config.json
```

Log lines name each function by its fully qualified name, so overrides that
share a method name stay distinguishable:

```
✨ Injected: StrategyEngine::Run()
✨ Injected: AlphaStrategy::Run()
✨ Injected: util::Reset()          free function, namespace only
✨ Injected: Normalize()            free function at file scope
```

## Config

Top level holds exactly one of `inject` or `remove` (never both), plus the
optional `exclude` and `include_dirs` keys.

```json
{
    "inject": [
        {
            "directory": "src/strategy",
            "file": "",
            "base_class": "IStrategy",
            "function": "Run"
        }
    ],

    "exclude": [
        { "directory": "src/strategy", "file": "StrategyEngine.cpp", "function": "Run" }
    ],

    "include_dirs": [ "include" ]
}
```

### Rule fields

All four are filters, ANDed together. An empty (or absent) field means
"no restriction on this dimension". Both modes accept all four: whatever an
`inject` rule can put in, the same rule under `remove` takes back out.

| Field | Meaning | Empty means |
|---|---|---|
| `directory` | Root to scan for `.cpp` files, recursively | current directory |
| `file` | Only `.cpp` files with this exact name | every `.cpp` found |
| `function` | Only functions with this exact name | every function |
| `base_class` | Only methods of a class that IS this class or derives from it, at any depth | no hierarchy filter |

`base_class` is for the "I don't know who implements/calls this virtual
function" case: name the base class and the tool finds every override down
the whole hierarchy, wherever those files happen to live.

Two things to know about it:

- **is-a semantics.** `"base_class": "A"` matches `A` itself as well as its
  descendants — when you are hunting for who calls a virtual function, `A`'s
  own implementation is a candidate too.
- **Access specifier is ignored.** `class B : private A` matches just like
  `class B : public A`. Private inheritance still overrides the virtual and
  still dispatches, so skipping it risks a silent miss.

`base_class` is rejected in `exclude` entries only — excluding works at the
directory/file/function level.

### What `remove` removes

`remove` mirrors `inject`, with one deliberate asymmetry:

- **Any filter present** (`function`, `base_class`, or a matching `exclude`)
  → the file is parsed and only the traces sitting at the top of the
  selected functions are deleted. Same selection pass as `inject`, so the
  same rule takes back out exactly what it put in, and the log names each
  function it removed from.
- **No filter at all** → no parsing, just a line scan that strips *every*
  `ScopeTrace` in the matched files. Slightly blunter, but it also catches
  traces the injector never placed (hand-written, or left over from a rule
  you have since edited). The log cannot name the function in this case,
  since there is no AST to ask.

### `directory` vs `include_dirs`

These answer different questions and are easy to confuse:

- `directory` — **where the `.cpp` files I want to modify live.** This tool's
  own scan scope.
- `include_dirs` — **where clang should look to resolve `#include`.** Exactly
  the compiler's `-I`. Affects parsing only; never selects a file for
  injection.

You need `include_dirs` when an `#include` is written relative to a project
include root rather than to the source file itself. The two fixture trees
under `test/` exist to show exactly this contrast.

**Interface next to the sources — `include_dirs` NOT needed** (`test/src`):

```
test/src/strategy/IStrategy.h            base class
test/src/strategy/StrategyEngine.cpp  ->  #include "StrategyEngine.h"
test/src/strategy/StrategyEngine.h    ->  #include "IStrategy.h"          same folder
test/src/strategy/alpha/AlphaStrategy.h -> #include "../StrategyEngine.h" relative
```

Every `#include` is relative to its own file, so clang resolves the whole
chain unaided. See `config_base_class_example.json` — no `include_dirs`.

**Interface in a separate include root — `include_dirs` REQUIRED**
(`test/proj`):

```
test/proj/include/framework/IExecutor.h        base class, outside the scan tree
test/proj/src/exec/OrderExecutor.h          ->  #include "framework/IExecutor.h"
test/proj/src/exec/fast/FastExecutor.h      ->  #include "../OrderExecutor.h"
```

`directory` is `test/proj/src`, but `IExecutor` lives under
`test/proj/include` and is included by include-root-relative path, so
`include_dirs` must list `test/proj/include`. See
`config_base_class_includedirs_example.json`.

Omit it and the failure is total but loud — clang cannot resolve
`IExecutor`, so `OrderExecutor` looks like it has no base class and the rule
matches nothing:

```
⚙️ Processing: test\proj\src\exec\OrderExecutor.cpp
   ⚠️  Parse error: 'framework/IExecutor.h' file not found
   ⚠️  Base-class matching may be incomplete — check "include_dirs" in the config.
Trace Injected : 0
```

`base_class` depends on this far more than the other filters do: matching by
function name needs no type information, matching by inheritance needs the
base class declaration to actually parse. That is why clang's diagnostics are
echoed to the log whenever a `base_class` rule is active — treat the warning
as "results are probably incomplete", not as noise.

Only **fatal** diagnostics are echoed, which in practice means an `#include`
clang could not resolve — precisely the failure that silently empties a
`base_class` match. Ordinary semantic errors are not reported: the hierarchy
still resolves through them, and one of them is guaranteed. Injected files
do not `#include "ScopeTrace.h"` (the tool never adds it), so every rerun
over an already-injected tree yields `unknown type name 'ScopeTrace'`.
Echoing that would train you to ignore the warning that matters.

## Known limitations

- **Headers are not scanned.** Only `.cpp` files, so a virtual function
  defined inline in a header (`void Run() override { ... }`) is never
  touched. This bites hardest with `base_class`, since subclass overrides
  are often one-liners in headers.
- **The `ScopeTrace` include is not added.** Injected files reference
  `ScopeTrace` without including its header, so they will not compile until
  you add it (a project-wide precompiled header is the usual answer).

## Examples

| File | Shows |
|---|---|
| `config_inject_example.json` | inject with a function-level `exclude` |
| `config_remove_example.json` | remove with a function-level `exclude` |
| `config_base_class_example.json` | every `Run()` override under `IStrategy`, no `include_dirs` needed |
| `config_base_class_includedirs_example.json` | every `Execute()` override under `IExecutor`, `include_dirs` required |

## Tests

```
python test/run_tests.py
```

Runs each rule against the fixture trees and asserts the exact set of
functions that received (or lost) a trace, then restores the fixtures.
Because the expected sets are exact, the classes that must NOT match are
asserted by their absence — `NetworkMgr::Run` (same method name, unrelated
class) and `LocalCache::Execute` (same method name, no base class).

Inject scenarios:

- interface beside the sources, `include_dirs` omitted → matches
- interface in a separate include root, `include_dirs` given → matches
- same, `include_dirs` omitted → warns and injects nothing
- `base_class` matches the base class's own implementation (is-a)
- `base_class` with an empty `function` → every method in the hierarchy
- labels stay fully qualified with no `base_class` filter in play
- free functions: namespace qualified, bare at file scope

Remove scenarios (each injects first, then removes, and asserts how many
traces are left behind):

- unfiltered rule strips the whole file, unnamed
- `function` only → every `Run()`, nothing else
- `base_class` → the overrides only, `LocalCache::Execute` survives
- `base_class` with `include_dirs` missing → warns, removes nothing
- function-level `exclude` → everything except the excluded `Run()`s

Plus a guard that every shipped `config_*example*.json` still passes
validation.

If `libclang.dll` is not on the DLL search path, point at it explicitly:

```
TRACE_INJECTOR_LIBCLANG=C:/Python/Lib/site-packages/clang/native/libclang.dll \
    python test/run_tests.py
```
